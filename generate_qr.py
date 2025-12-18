import os
import qrcode

BASE_URL = "http://192.168.1.8:5001"  # <-- il tuo IP/porta che funzionano dal telefono

os.makedirs("static/qr", exist_ok=True)

links = {
    "tamburi": f"{BASE_URL}/g/tamburi",
    "chiarine": f"{BASE_URL}/g/chiarine",
}

for name, url in links.items():
    img = qrcode.make(url)
    img.save(f"static/qr/{name}.png")
    print(f"Creato: static/qr/{name}.png  ->  {url}")
