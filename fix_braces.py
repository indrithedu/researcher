import re

with open('report_generator.py', 'r') as f:
    content = f.read()

# Find the f-string block
# It starts with html = f"""<!DOCTYPE html>
# and ends with """

# We want to find CSS blocks and double the braces
# A better way: look for patterns like .something { ... } that are NOT already {{ ... }}

def double_braces(match):
    full_match = match.group(0)
    # If already doubled, return as is
    if full_match.startswith('{{') or '{{' in full_match:
        return full_match
    
    # Replace { with {{ and } with }}
    # But be careful not to double already doubled ones if we re-run
    # Actually, let's just target the specific blocks we found
    
    # Simple heuristic: if it's a CSS-like block with single braces
    # e.g. .name { prop: value; }
    res = full_match.replace('{', '{{').replace('}', '}}')
    return res

# Regex to match CSS blocks with single braces
# This is tricky because f-strings might have {variable}
# But CSS usually has : and ;
css_pattern = re.compile(r'\.[a-zA-Z0-9_-]+\s*\{[^}]+\}')

new_content = css_pattern.sub(double_braces, content)

# Also match media queries if any
media_pattern = re.compile(r'@media[^{]+\{[^{}]+\{[^}]+\}\s*\}')
# This is getting complex.

# Alternative: just replace the whole block of CSS precisely.
# I'll just do it manually with a few large EditFile calls.
