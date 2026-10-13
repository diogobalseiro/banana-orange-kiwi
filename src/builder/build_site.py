import json
import os

def load_data(data_dir):
    known_retailers = [
        ('continente', 'Continente'),
        ('zu', 'ZU'),
        ('zooplus', 'Zooplus')
    ]
    wet_products = []
    dry_products = []

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
        if 'smaak' in (p.get('b') or '').lower() and p.get('k'):
            p['s'] = max(p.get('s', 0), 75)
            p['t'] = 'Tier A (Excelente / Alto Teor Carne)'

    for p in dry_products:
        if 'k' not in p:
            name_l = (p.get('n') or '').lower()
            p['k'] = any(k in name_l for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote'])

    wet_products.sort(key=lambda x: (x.get('s', 0) or 0, x.get('vr', 0) or 0.0), reverse=True)
    dry_products.sort(key=lambda x: (x.get('s', 0) or 0, x.get('vr', 0) or 0.0), reverse=True)

    return wet_products, dry_products

def generate_html(wet_products, dry_products, output_path):
    builder_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(builder_dir, 'template.html')

    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()

    wet_json_str = json.dumps(wet_products, ensure_ascii=False)
    dry_json_str = json.dumps(dry_products, ensure_ascii=False)

    html_content = template_content.replace('/*__WET_DATA__*/ []', wet_json_str)
    html_content = html_content.replace('/*__DRY_DATA__*/ []', dry_json_str)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[Builder] Successfully generated dashboard at {output_path}")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, 'data')
    output_path = os.path.join(base_dir, 'index.html')
    
    wet, dry = load_data(data_dir)
    print(f"[Builder] Loaded {len(wet)} wet products and {len(dry)} dry products.")
    generate_html(wet, dry, output_path)

if __name__ == '__main__':
    main()
