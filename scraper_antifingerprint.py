#!/usr/bin/env python3
"""
PedidosYa scraper v4 - Bypass PerimeterX.
Estrategia: generar actividad de mouse real ANTES de que PerimeterX cargue,
y asegurar que todos los checks del script PX pasen.
"""
import asyncio
import websockets
import json
import subprocess
import urllib.request
import os
import sys
import base64
import random


async def main():
    url = "https://www.pedidosya.cr/restaurantes/grecia/pollos-teddys-grecia-42721e19-990e-4b26-9f45-3a215cf47569-menu"
    profile_dir = "/media/disco1tb/hermes-cosas/espacio-de-trabajo/pollos teddy's/.browser_profile"
    
    chrom = subprocess.Popen([
        "/usr/bin/chromium", "--headless=new", "--no-sandbox",
        "--disable-gpu", "--disable-dev-shm-usage",
        "--remote-debugging-port=9232", "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars", "--no-first-run", "--no-default-browser-check",
        "--lang=es-CR,es,en-US,en",
        "--window-size=1920,1080",
        "--disable-features=Translate,AcceptCHFrame",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        await asyncio.sleep(4)
        with urllib.request.urlopen("http://127.0.0.1:9232/json") as resp:
            tabs = json.loads(resp.read())
        ws_url = tabs[0]["webSocketDebuggerUrl"]
        
        async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
            _id = [0]
            
            async def send_cmd(method, params=None, session=None):
                _id[0] += 1
                msg = {"id": _id[0], "method": method}
                if params: msg["params"] = params
                if session: msg["sessionId"] = session
                await ws.send(json.dumps(msg))
                while True:
                    d = json.loads(await ws.recv())
                    if d.get("id") == _id[0]: return d
            
            async def ev(expr, session=None):
                r = await send_cmd("Runtime.evaluate",
                    {"expression": expr, "returnByValue": True}, session)
                return r.get("result", {}).get("result", {}).get("value")
            
            async def mouse_move(x, y):
                await send_cmd("Input.dispatchMouseEvent", {
                    "type": "mouseMoved", "x": x, "y": y,
                    "button": "none", "buttons": 0
                })
            
            await send_cmd("Page.enable")
            await send_cmd("Runtime.enable")
            await send_cmd("Network.enable")
            await send_cmd("Fetch.enable", {"patterns": [{"urlPattern": "*captcha.px-cloud*", "requestStage": "Request"}]})
            
            # Anti-detect script - se ejecuta ANTES que cualquier script de la pagina
            anti_detect = """
(function() {
    const overrides = {
        webdriver: undefined,
        platform: 'Win32',
        hardwareConcurrency: 8,
        deviceMemory: 8,
        maxTouchPoints: 0,
        vendor: 'Google Inc.',
    };
    for (const [k,v] of Object.entries(overrides)) {
        try { Object.defineProperty(navigator, k, {get:()=>v,configurable:true,enumerable:true}); } catch(e) {}
    }
    Object.defineProperty(navigator, 'languages', {get:()=>['es-CR','es','en-US','en'],configurable:true});
    Object.defineProperty(navigator, 'language', {get:()=>'es-CR',configurable:true});
    
    const pdf = {name:'Chrome PDF Plugin',filename:'internal-pdf-viewer',description:'PDF',length:1};
    const pdfView = {name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',description:'',length:1};
    const nacl = {name:'Native Client',filename:'internal-nacl-plugin',description:'',length:1};
    const plugins = [pdf,pdfView,nacl];
    plugins.item = (i)=>plugins[i];
    plugins.namedItem = (n)=>plugins.find(p=>p.name===n);
    plugins.refresh = ()=>{};
    plugins[Symbol.iterator] = function*(){yield*this;};
    Object.defineProperty(plugins,'length',{get:()=>3});
    Object.defineProperty(navigator,'plugins',{get:()=>plugins,configurable:true});
    Object.defineProperty(navigator,'mimeTypes',{get:()=>({length:0,item:()=>null,namedItem:()=>null}),configurable:true});
    
    window.chrome = window.chrome||{};
    window.chrome.runtime = {connect:function(){},sendMessage:function(){},id:undefined};
    
    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if(p===37445) return 'Google Inc. (NVIDIA)';
        if(p===37446) return 'ANGLE (NVIDIA, GTX 1050 Ti)';
        return origGetParam.call(this,p);
    };
    
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = function(p) {
        if(p&&p.name==='notifications') return Promise.resolve({state:'prompt',onchange:null});
        return origQuery(p);
    };
    
    Object.defineProperty(screen,'width',{get:()=>1920});
    Object.defineProperty(screen,'height',{get:()=>1080});
    Object.defineProperty(screen,'availWidth',{get:()=>1920});
    Object.defineProperty(screen,'availHeight',{get:()=>1040});
    Object.defineProperty(screen,'colorDepth',{get:()=>24});
    Object.defineProperty(screen,'pixelDepth',{get:()=>24});
    
    // Eliminar rastros CDP
    Object.keys(window).filter(k=>k.startsWith('cdc_')||k.startsWith('$cdc_')).forEach(k=>{ try{delete window[k];}catch(e){} });
})();
"""
            r = await send_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": anti_detect})
            print(f"Anti-detect script id: {r.get('result',{}).get('identifier')}")
            
            # PRIMERO: navegar a pedidosya.cr主页 para simular comportamiento natural
            print("\n[1] Navegando a PedidosYa homepage primero...")
            await send_cmd("Page.navigate", {"url": "https://www.pedidosya.cr/"})
            await asyncio.sleep(8)
            
            # Generar mouse movements en la página principal - comportamiento humano
            print("[2] Simulando comportamiento humano (scroll, mouse)...")
            for _ in range(5):
                x = random.randint(200, 1700)
                y = random.randint(100, 800)
                await mouse_move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.4))
            
            # Scroll down
            await ev("window.scrollBy(0, 300)")
            await asyncio.sleep(1)
            
            # Navegar directamente al menú
            print("[3] Navegando al menú de Pollos Teddy's Grecia...")
            await send_cmd("Page.navigate", {"url": url})
            
            # Monitear por 30 segundos
            print("[4] Monitoreando carga (30s)...")
            deadline = asyncio.get_event_loop().time() + 30
            blocked = False
            
            while asyncio.get_event_loop().time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    d = json.loads(msg)
                    method = d.get("method","")
                    
                    if method == "Page.frameNavigated":
                        frame = d.get("params",{}).get("frame",{})
                        u = frame.get("url","")
                        print(f"  nav: {u[:100]}")
                    
                    elif method == "Fetch.requestPaused":
                        # Interceptar la petición al captcha de PerimeterX
                        req_id = d["params"]["requestId"]
                        req_url = d["params"]["request"]["url"]
                        print(f"  ⚠️  Blocked request: {req_url[:80]}")
                        # Dejar pasar la petición
                        await send_cmd("Fetch.continueRequest", {"requestId": req_id})
                    
                    elif method == "Page.loadEventFired":
                        print(f"  [load event]")
                        
                except asyncio.TimeoutError:
                    # Generar mouse movements periódicamente
                    if random.random() > 0.7:
                        await mouse_move(random.randint(300, 1600), random.randint(200, 700))
            
            # Verificar resultado
            html = await ev("document.documentElement.outerHTML") or ""
            title = await ev("document.title") or ""
            final_url = await ev("window.location.href") or ""
            
            with open("/media/disco1tb/hermes-cosas/espacio-de-trabajo/menu_pedidosya.html", "w") as f:
                f.write(html)
            
            print(f"\n{'='*60}")
            print(f"URL: {final_url[:100]}")
            print(f"Título: {title}")
            print(f"HTML: {len(html)} chars")
            
            low = html.lower()
            if "px-captcha" in low or "perimeterx" in low or "captcha" in low.lower():
                print("⚠️ PerimeterX captcha detectado pero podemos intentar resolver...")
                
                # Buscar el iframe de PerimeterX y tratar de interactuar
                iframe_info = await ev("""
                (function() {
                    var frames = document.querySelectorAll('iframe');
                    var info = [];
                    frames.forEach(function(f) {
                        var r = f.getBoundingClientRect();
                        info.push({src: f.src, id: f.id, token: f.getAttribute('token'),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            display: window.getComputedStyle(f).display,
                            visibility: window.getComputedStyle(f).visibility
                        });
                    });
                    return JSON.stringify(info);
                })()
                """)
                print(f"Iframes: {iframe_info}")
                
            elif "pollos" in low or "teddy" in low or "menú" in low:
                print(f"✅ ¡MENÚ OBTENIDO! ({len(html)} chars)")
            else:
                print(f"? Estado desconocido")
                # Verificar checks
                check = await ev("""JSON.stringify({
                    webdriver: navigator.webdriver,
                    platform: navigator.platform,
                    plugins: navigator.plugins.length,
                    screen: screen.width+'x'+screen.height
                })""")
                print(f"Browser: {check}")
    
    finally:
        chrom.terminate()
        chrom.wait()


if __name__ == "__main__":
    asyncio.run(main())
