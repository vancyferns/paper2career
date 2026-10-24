import json
import os
from datetime import datetime

def generate_sitemap():
    base_url = "https://paper2career.vercel.app"
    data_path = "frontend/public/demo-data.json"
    sitemap_path = "frontend/public/sitemap.xml"
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    urls = [
        f"""  <url>
    <loc>{base_url}/</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""
    ]
    
    if os.path.exists(data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            jobs = data.get("jobs", [])
            for j in jobs:
                jid = j.get("$id")
                lastmod = j.get("last_seen_at") or today_str
                if jid:
                    urls.append(f"""  <url>
    <loc>{base_url}/?job={jid}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>""")
                    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
"""
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(xml_content.strip() + "\n")
    print(f"Generated {sitemap_path} with {len(urls)} URLs.")

if __name__ == "__main__":
    generate_sitemap()
