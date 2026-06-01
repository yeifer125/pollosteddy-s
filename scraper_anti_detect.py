#!/usr/bin/env python3
"""
Scraper PedidosYa - Enfoque headless con todas las anti-detección flags.
Usa user-data-dir persistente para que las cookies de Cloudflare persistan.
"""
import asyncio
import websockets
import json
import subprocess
import urllib.request
import os
import sys

sys.path.insert(0, '/media/disco1tb/hermes-cosas/espacio-de-trabajo/browser-use-env/lib/python3.11/site-packages')


async def navigate_and_extract(ws_url, target_url, wait_sec=45):
    """Navega y extrae HTML después de esperar."""
    async with websockets.connect(ws_url, max_size=100 * 1024 * 1024) as ws:
        cmd_id = [0]

        async def send(method, params=None):
            cmd_id[0] += 1
            msg = {"id": cmd_id[0], "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            while True:
                data = json.loads(await ws.recv())
                if data.get("id") == cmd_id[0]:
                    return data

        await send("Page.enable")
        await send("Runtime.enable")
        await send("Network.enable")

        # Anti-detección: override navigator.webdriver y más
        await send("Runtime.evaluate", {
            "expression": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                    {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                    {name: 'Native Client', filename: 'internal-nacl-plugin'}
                ]
            });
            Object.defineProperty(navigator, 'languages', {get: () => ['es-CR', 'es', 'en-US', 'en']});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({state: Notification.permission}) :
                    originalQuery(parameters)
            );
            // WebGL vendor
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Google Inc. (NVIDIA)';
                if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return getParameter.call(this, parameter);
            };
            """
        })

        # Navigate
        print(f"Navegando a: {target_url}")
        await send("Page.navigate", {"url": target_url})

        # Esperar drain de eventos
        print(f"Esperando {wait_sec}s...")
        deadline = asyncio.get_event_loop().time() + wait_sec
        while asyncio.get_event_loop().time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                d = json.loads(msg)
                m = d.get("method", "")
                if m == "Page.loadEventFired":
                    print("  -> loadEventFired")
                elif m == "Page.frameNavigated":
                    url = d.get("params", {}).get("frame", {}).get("url", "")
                    if url:
                        print(f"  -> navigated: {url[:80]}")
            except asyncio.TimeoutError:
                continue

        # Get HTML
        resp = await send("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
            "returnByValue": True
        })
        return resp.get("result", {}).get("result", {}).get("value", "")


async def main():
    target_url = "https://www.pedidosya.cr/restaurantes/grecia/pollos-teddys-grecia-42721e19-990e-4b26-9f45-3a215cf47569-menu"
    
    # Directorio persistente para cookies/cache
    profile_dir = "/media/disco1tb/hermes-cosas/espacio-de-trabajo/pollos teddy's/.browser_profile"
    os.makedirs(profile_dir, exist_ok=True)
    
    # Lanzar Chromium anti-detección
    print("Lanzando Chromium con flags anti-detección...")
    chrom = subprocess.Popen([
        "/usr/bin/chromium",
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--remote-debugging-port=9224",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--lang=es",
        # Anti-bot bypass flags
        "--disable-blink-features=AutomationControlled",
        "--disable-features=AutomationControlled",
        "--ignore-certificate-errors",
        "--allow-running-insecure-content",
        "--window-size=1920,1080",
        "--start-maximized",
        # DNS y networking
        "--dns-prefetch-disable",
        "--disable-background-networking=false",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        "--disable-features=AcceptCHFrame",
        "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        await asyncio.sleep(4)
        
        # Obtener WebSocket URL
        with urllib.request.urlopen("http://127.0.0.1:9224/json") as resp:
            tabs = json.loads(resp.read())
        ws_url = tabs[0]["webSocketDebuggerUrl"]
        print(f"CDP conectado: {ws_url}")
        
        html = await navigate_and_extract(ws_url, target_url, wait_sec=45)
        
        # Guardar resultado
        output = "/media/disco1tb/hermes-cosas/espacio-de-trabajo/menu_pedidosya.html"
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        
        print(f"\nHTML guardado: {output} ({len(html)} chars)")
        
        # Analizar
        low = html.lower()
        if "just a moment" in low or "verificando" in low:
            print("❌ Cloudflare Turnstile - BLOQUEADO")
        elif "cf-turnstile" in low or "cf-chl" in low:
            print("❌ Cloudflare challenge presente")
        elif "pollos" in low and ("teddy" in low or "menu" in low) and "404" not in low:
            print("✅ ¡MENÚ OBTENIDO!")
            # Imprimir preview
            start = low.find("pollos")
            print(html[max(0,start-100):start+500])
        else:
            print(f"? Resultado: {html[:300]}")
    
    finally:
        chrom.terminate()
        chrom.wait()


if __name__ == "__main__":
    asyncio.run(main())
