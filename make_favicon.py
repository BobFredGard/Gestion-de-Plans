import base64

svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1a3a6b"/>
      <stop offset="100%" stop-color="#2a5a9b"/>
    </linearGradient>
    <linearGradient id="pen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#8b7cc8"/>
      <stop offset="100%" stop-color="#55449a"/>
    </linearGradient>
  </defs>
  <circle cx="32" cy="32" r="30" fill="url(#bg)"/>
  <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
  <!-- Pen body -->
  <rect x="22" y="10" width="20" height="36" rx="4" fill="url(#pen)" stroke="#44337a" stroke-width="1.5"/>
  <!-- Pen cap -->
  <rect x="22" y="8" width="20" height="6" rx="3" fill="#d4c9b8" stroke="#a89d8c" stroke-width="1.2"/>
  <!-- Clip -->
  <rect x="38" y="4" width="5" height="14" rx="2.5" fill="#d4c9b8" stroke="#a89d8c" stroke-width="1.2"/>
  <!-- Tip -->
  <polygon points="24,46 40,46 32,54" fill="#d4c9b8" stroke="#a89d8c" stroke-width="1.2"/>
  <polygon points="30,54 34,54 32,58" fill="#333"/>
  <!-- Highlight -->
  <rect x="24" y="12" width="4" height="32" rx="2" fill="rgba(255,255,255,0.15)"/>
  <!-- Text NP -->
  <text x="32" y="38" text-anchor="middle" font-family="Arial,sans-serif" font-weight="bold" font-size="11" fill="#ffffff">NP</text>
</svg>"""

with open(r'D:\ServerFolders\NumPlans\favicon.svg', 'w') as f:
    f.write(svg)

print(f'SVG saved ({len(svg)} bytes)')

# Convert SVG to ICO via PIL - render SVG to PNG first
try:
    import cairosvg
    png_data = cairosvg.svg2png(bytestring=svg.encode(), output_width=32, output_height=32)
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(png_data))
    img.save(r'D:\ServerFolders\NumPlans\favicon.png', format='PNG')
    img.save(r'D:\ServerFolders\NumPlans\favicon.ico', format='ICO', sizes=[(32,32)])
    print('PNG/ICO saved from SVG')
except ImportError:
    print('cairosvg not available, SVG favicon will be used directly')
    # Can still use SVG as favicon via data URI or direct link
