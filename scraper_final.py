#!/usr/bin/env python3
"""
PediosYa scraper - Turnstile via Shadow DOM en session del iframe.
Ahora que sabemos que challenges.cloudflare.com es un target separado,
accedemos a su DOM y buscamos el checkbox en shadow DOM.
"""
import asyncio
import websockets
import json
import subprocess
import urllib.request
import os
import sys
import base64


async def find_checkbox_in_shadow_dom(evaluate_fn):
    """Busca el checkbox de Turnstile traversando shadow DOMs."""
    result = await evaluate_fn("""
    (function() {
        // Buscar todos los elementos con shadowRoot
        function searchShadowDOM(root, depth) {
            if (depth > 10) return null;
            
            // Buscar checkbox en este nivel
            var candidates = root.querySelectorAll('[role="checkbox"], input[type="checkbox"], [class*="checkbox"], [class*="checkmark"], [id*="checkbox"]');
            for (var c of candidates) {
                var r = c.getBoundingClientRect();
                if (r.width > 10 && r.height > 10) {
                    return {
                        found: true, depth: depth,
                        tag: c.tagName, id: c.id,
                        cls: (c.className || '').substring(0, 60),
                        aria: c.getAttribute('aria-label') || '',
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height)
                    };
                }
            }
            
            // Buscar en shadow DOMs
            var all = root.querySelectorAll('*');
            for (var el of all) {
                if (el.shadowRoot) {
                    var found = searchShadowDOM(el.shadowRoot, depth + 1);
                    if (found) return found;
                }
            }
            
            // Buscar si es un slot
            var slots = root.querySelectorAll('slot');
            for (var slot of slots) {
                var assigned = slot.assignedElements();
                for (var a of assigned) {
                    if (a.shadowRoot) {
                        var found = searchShadowDOM(a.shadowRoot, depth + 1);
                        if (found) return found;
                    }
                }
            }
            
            return null;
        }
        
        // También buscar por atributos de Turnstile
        var turnstile_el = document.querySelector('[data-callback], [data-sitekey], iframe[src*="challenges.cloudflare"]');
        
        var found = searchShadowDOM(document, 0);
        
        if (!found) {
            // Reportar qué hay en el body
            var body_html = document.body ? document.body.innerHTML.substring(0, 500) : 'no body';
            var all_els = [];
            document.querySelectorAll('*').forEach(function(el) {
                if (el.shadowRoot) {
                    all_els.push(el.tagName + '#' + el.id + ' (has shadow)');
                }
            });
            return JSON.stringify({found: false, body: body_html, shadow_hosts: all_els});
        }
        
        return JSON.stringify(found);
    })()
    """)
    return result


async def main():
    url = "https://www.pedidosya.cr/restaurantes/grecia/pollos-teddys-grecia-42721e19-990e-4b26-9f45-3a215cf47569-menu"
    profile_dir = "/media/disco1tb/hermes-cosas/espacio-de-trabajo/pollos teddy's/.browser_profile"
    
    chrom = subprocess.Popen([
        "/usr/bin/chromium", "--headless=new", "--no-sandbox",
        "--disable-gpu", "--disable-dev-shm-usage",
        "--remote-debugging-port=9228", "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1920,1080", "--lang=es", "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        await asyncio.sleep(4)
        with urllib.request.urlopen("http://127.0.0.1:9228/json") as resp:
            tabs = json.loads(resp.read())
        ws_url = tabs[0]["webSocketDebuggerUrl"]
        print(f"CDP: {ws_url}")
        
        async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
            _id = [0]
            pending_events = []
            
            async def send_cmd(method, params=None, session=None):
                _id[0] += 1
                msg = {"id": _id[0], "method": method}
                if params: msg["params"] = params
                if session: msg["sessionId"] = session
                await ws.send(json.dumps(msg))
                while True:
                    d = json.loads(await ws.recv())
                    if d.get("id") == _id[0]:
                        return d
                    pending_events.append(d)
            
            async def evaluate(expr, session=None):
                r = await send_cmd("Runtime.evaluate",
                    {"expression": expr, "returnByValue": True}, session)
                return r.get("result", {}).get("result", {}).get("value")
            
            async def screenshot(path):
                r = await send_cmd("Page.captureScreenshot", {"format": "jpeg", "quality": 70})
                data = r.get("result", {}).get("data", "")
                if data:
                    with open(path, "wb") as f:
                        f.write(base64.b64decode(data))
            
            await send_cmd("Page.enable")
            await send_cmd("Runtime.enable")
            
            # Navegar
            print("Navegando...")
            await send_cmd("Page.navigate", {"url": url})
            await asyncio.sleep(25)
            
            # Encontrar target del iframe Cloudflare
            targets = await send_cmd("Target.getTargets")
            all_targets = targets.get("result", {}).get("targetInfos", [])
            
            cf_target = None
            for t in all_targets:
                if "challenges.cloudflare" in t.get("url", ""):
                    cf_target = t
                    break
            
            if not cf_target:
                print("❌ No se encontró target de Cloudflare")
                html = await evaluate("document.documentElement.outerHTML") or ""
                with open("/media/disco1tb/hermes-cosas/espacio-de-trabajo/menu_pedidosya.html", "w") as f:
                    f.write(html)
                return
            
            print(f"✅ Cloudflare target: {cf_target['url'][:80]}")
            
            # Attach al target
            att = await send_cmd("Target.attachToTarget", {"targetId": cf_target["targetId"], "flatten": True})
            sid = att.get("result", {}).get("sessionId")
            print(f"Session: {sid}")
            
            if not sid:
                print("❌ No se pudo attach")
                return
            
            await asyncio.sleep(2)
            
            # Guardar DOM del frame para análisis
            dom = await evaluate("document.documentElement.outerHTML", sid) or ""
            with open("/media/disco1tb/hermes-cosas/espacio-de-trabajo/cf_dom.html", "w") as f:
                f.write(dom)
            print(f"DOM del frame: {len(dom)} chars")
            
            # Buscar checkbox en shadow DOM
            print("\nBuscando checkbox en shadow DOM...")
            chk_json = await find_checkbox_in_shadow_dom(lambda expr, session=None: evaluate(expr, sid))
            print(f"Resultado: {chk_json}")
            
            if chk_json:
                try:
                    chk = json.loads(chk_json)
                except:
                    chk = None
                
                if chk and chk.get("found"):
                    cx, cy = chk["x"], chk["y"]
                    print(f"\n✅ Checkbox encontrado en ({cx},{cy}) - {chk}")
                    
                    # Click en la sesión del frame
                    print("Haciendo click...")
                    await send_cmd("Input.dispatchMouseEvent", {
                        "type": "mousePressed", "x": cx, "y": cy,
                        "button": "left", "clickCount": 1, "buttons": 1
                    }, sid)
                    await asyncio.sleep(0.5)
                    await send_cmd("Input.dispatchMouseEvent", {
                        "type": "mouseReleased", "x": cx, "y": cy,
                        "button": "left", "clickCount": 1, "buttons": 0
                    }, sid)
                    
                    print("Click enviado. Esperando 15s...")
                    await asyncio.sleep(15)
                elif chk:
                    print(f"\n❌ No se encontró checkbox. Info: {chk}")
                    
                    # Intentar hacer click en el centro del frame
                    dims_str = await evaluate("JSON.stringify({w: window.innerWidth, h: window.innerHeight})", sid)
                    if dims_str:
                        dims = json.loads(dims_str)
                        cx = dims["w"] // 2
                        cy = dims["h"] // 2
                        print(f"Intentando click en centro del frame ({cx},{cy})...")
                        await send_cmd("Input.dispatchMouseEvent", {
                            "type": "mousePressed", "x": cx, "y": cy,
                            "button": "left", "clickCount": 1, "buttons": 1
                        }, sid)
                        await asyncio.sleep(0.5)
                        await send_cmd("Input.dispatchMouseEvent", {
                            "type": "mouseReleased", "x": cx, "y": cy,
                            "button": "left", "clickCount": 1, "buttons": 0
                        }, sid)
                        await asyncio.sleep(15)
            
            # Verificar resultado final
            final_html = await evaluate("document.documentElement.outerHTML") or ""
            with open("/media/disco1tb/hermes-cosas/espacio-de-trabajo/menu_pedidosya.html", "w") as f:
                f.write(final_html)
            
            low = final_html.lower()
            if "just a moment" not in low and "turnstile" not in low and "verificando" not in low:
                if "pollos" in low or "teddy" in low:
                    print(f"\n✅ ¡ÉXITO! Menú de PedidosYa obtenido ({len(final_html)} chars)")
                else:
                    print(f"\n? Página cargada ({len(final_html)} chars)")
            else:
                print(f"\n❌ Aún bloqueado ({len(final_html)} chars)")
                await screenshot("/media/disco1tb/hermes-cosas/espacio-de-trabajo/debug_final.jpg")
                
                # Guardar también el DOM del frame para debug
                cf_dom = await evaluate("document.documentElement.outerHTML", sid) or ""
                with open("/media/disco1tb/hermes-cosas/espacio-de-trabajo/cf_dom_final.html", "w") as f:
                    f.write(cf_dom)
    
    finally:
        chrom.terminate()
        chrom.wait()


if __name__ == "__main__":
    asyncio.run(main())
