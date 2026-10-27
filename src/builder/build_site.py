import json
import os
from src.pipeline.manifest import load_manifest, atomic_replace

def load_data(data_dir, manifest=None):
    if manifest is None:
        manifest = load_manifest(data_dir)

    known_retailers = [
        ('continente', 'Continente'),
        ('zu', 'ZU'),
        ('zooplus', 'Zooplus')
    ]
    retailer_map = {k: v for k, v in known_retailers}

    wet_products = []
    dry_products = []

    datasets = manifest.get("datasets", {})
    if datasets:
        for key, meta in datasets.items():
            if meta.get("status") != "accepted":
                continue
            path = os.path.join(data_dir, f"{key}.json")
            if not os.path.exists(path):
                continue
            prefix = key.split('_')[0]
            display_name = retailer_map.get(prefix, prefix.capitalize())
            with open(path, 'r', encoding='utf-8') as f:
                prods = json.load(f)
                for p in prods:
                    if not p.get('r'):
                        p['r'] = display_name
                if key.endswith('_wet'):
                    wet_products.extend(prods)
                elif key.endswith('_dry'):
                    dry_products.extend(prods)
    else:
        for prefix, display_name in known_retailers:
            w_path = os.path.join(data_dir, f"{prefix}_wet.json")
            d_path = os.path.join(data_dir, f"{prefix}_dry.json")

            if os.path.exists(w_path):
                with open(w_path, 'r', encoding='utf-8') as f:
                    prods = json.load(f)
                    for p in prods:
                        if not p.get('r'):
                            p['r'] = display_name
                    wet_products.extend(prods)

            if os.path.exists(d_path):
                with open(d_path, 'r', encoding='utf-8') as f:
                    prods = json.load(f)
                    for p in prods:
                        if not p.get('r'):
                            p['r'] = display_name
                    dry_products.extend(prods)

    # Ensure kitten flag consistency
    for p in wet_products:
        if 'k' not in p:
            name_l = (p.get('n') or '').lower()
            p['k'] = any(k in name_l for k in ['júnior', 'junior', 'kitten', 'gatinho'])

    for p in dry_products:
        if 'k' not in p:
            name_l = (p.get('n') or '').lower()
            p['k'] = any(k in name_l for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote'])

    wet_products.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)
    dry_products.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)

    return wet_products, dry_products

def generate_html(wet_products, dry_products, output_path, manifest_data=None):
    builder_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(builder_dir, 'template.html')

    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()

    wet_json_str = json.dumps(wet_products, ensure_ascii=False)
    dry_json_str = json.dumps(dry_products, ensure_ascii=False)
    manifest_json_str = json.dumps(manifest_data or {}, ensure_ascii=False)

    html_content = template_content.replace('/*__WET_DATA__*/ []', wet_json_str)
    html_content = html_content.replace('/*__DRY_DATA__*/ []', dry_json_str)
    html_content = html_content.replace('/*__MANIFEST_DATA__*/ {}', manifest_json_str)

    # Atomic write to protect against interrupted publication
    temp_path = output_path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    atomic_replace(temp_path, output_path)
    print(f"[Builder] Successfully generated dashboard at {output_path}")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, 'data')
    output_path = os.path.join(base_dir, 'index.html')
    
    manifest = load_manifest(data_dir)
    wet, dry = load_data(data_dir, manifest=manifest)
    print(f"[Builder] Loaded {len(wet)} wet products and {len(dry)} dry products.")
    generate_html(wet, dry, output_path, manifest_data=manifest)

if __name__ == '__main__':
    main()
