#!/usr/bin/env python3
"""
Deep debug: explorar la estructura completa del frame de Cloudflare Turnstile
para encontrar dónde está el checkbox.
"""
import asyncio
import websockets
import json
import subprocess
import urllib.request
import os
import sys
import base64


async def main():
    url = "https://www.pedidosya.cr/restaurantes/grecia/pollos-teddys-grecia-42721e19-990e-4b26-9f45-3a215cf47569-menu"
    profile_dir = "/media/disco1tb/hermes-cosas/espacio-de-trabajo/pollos teddy's/.browser_profile"
    
    chrom = subprocess.Popen([
        "/usr/bin/chromium", "--headless=new", "--no-sandbox",
        "--disable-gpu", "--disable-dev-shm-usage",
        "--remote-debugging-port=9229", "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--window-size=1920,1080", "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        await asyncio.sleep(4)
        with urllib.request.urlopen("http://127.0.0.1:9229/json") as resp:
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
            
            await send_cmd("Page.enable")
            await send_cmd("Runtime.enable")
            await send_cmd("DOM.enable")
            
            print("Navegando...")
            await send_cmd("Page.navigate", {"url": url})
            await asyncio.sleep(30)
            
            # Obtener TODOS los targets
            targets = await send_cmd("Target.getTargets")
            all_targets = targets.get("result", {}).get("targetInfos", [])
            print(f"\nTodos los targets ({len(all_targets)}):")
            for t in all_targets:
                print(f"  [{t.get('type')}] {t.get('url','')[:120]}")
            
            # Buscar TODOS los frames con getFrameTree recursivo
            tree = await send_cmd("Page.getFrameTree")
            
            def print_tree(node, indent=0):
                frame = node.get("frame", {})
                url_f = frame.get("url", "")
                fid = frame.get("id", "")[:20]
                mime = frame.get("mimeType", "")
                print(f"{'  '*indent}[frame] {url_f[:100]} (id={fid} mime={mime})")
                for child in node.get("childFrames", []):
                    print_tree(child, indent+1)
            
            print("\nFrame tree:")
            print_tree(tree.get("result", {}).get("frameTree", {}))
            
            # Encontrar targets de Cloudflare
            cf_targets = [t for t in all_targets if "challenges.cloudflare" in t.get("url","") or "cf-" in t.get("url","").lower()]
            
            for cf in cf_targets:
                print(f"\n=== Analizando target Cloudflare: {cf['url'][:100]} ===")
                att = await send_cmd("Target.attachToTarget", {"targetId": cf["targetId"], "flatten": True})
                sid = att.get("result", {}).get("sessionId")
                
                if not sid:
                    continue
                    
                await asyncio.sleep(1)
                
                # Obtener documento DOM
                doc = await send_cmd("DOM.getDocument", {"depth": -1, "pierce": True}, sid)
                root_node_id = doc.get("result", {}).get("root", {}).get("nodeId")
                
                if root_node_id:
                    # Obtener outerHTML
                    html_r = await send_cmd("DOM.getOuterHTML", {"nodeId": root_node_id}, sid)
                    html = html_r.get("result", {}).get("outerHTML", "")
                    print(f"HTML length: {len(html)}")
                    print(f"HTML preview:\n{html[:1000]}")
                    
                    # Guardar
                    safe_name = cf["url"].replace("/","_").replace(":","")[:80]
                    with open(f"/media/disco1tb/hermes-cosas/espacio-de-trabajo/cf_frame_{safe_name}.html", "w") as f:
                        f.write(html)
                
                # Buscar con JS - usar pierce para atravesar iframes
                result = await ev("""
                (function() {
                    // Buscar iframes dentro de este frame
                    var iframes = document.querySelectorAll('iframe');
                    var info = [];
                    iframes.forEach(function(f) {
                        var r = f.getBoundingClientRect();
                        info.push({
                            src: (f.src || '').substring(0,100),
                            id: f.id, cls: f.className,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            title: f.title || ''
                        });
                    });
                    
                    // Buscar elementos con shadow DOM
                    var shadowHosts = [];
                    document.querySelectorAll('*').forEach(function(el) {
                        if (el.shadowRoot) {
                            shadowHosts.push(el.tagName + '#' + el.id + '.' + el.className.substring(0,30));
                        }
                    });
                    
                    return JSON.stringify({
                        url: window.location.href,
                        body_child_count: document.body ? document.body.childElementCount : -1,
                        body_html: document.body ? document.body.innerHTML.substring(0,500) : 'no body',
                        iframes: info,
                        shadow_hosts: shadowHosts,
                        title: document.title
                    });
                })()
                """, sid)
                
                if result:
                    data = json.loads(result)
                    print(f"\nFrame info: {json.dumps(data, indent=2, ensure_ascii=False)[:2000]}")
                
                # Obtener child frames de este frame
                try:
                    child_tree = await send_cmd("Page.getFrameTree", {}, sid)
                    print(f"\nChild frames del target Cloudflare:")
                    print_tree(child_tree.get("result", {}).get("frameTree", {}))
                except:
                    pass
    
    finally:
        chrom.terminate()
        chrom.wait()


if __name__ == "__main__":
    asyncio.run(main())
