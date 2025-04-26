# arka_uc.py
import os
import sys
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict
from cachetools import cached, TTLCache, keys
import math

# --- Ayarlar ---
API_ANAHTARI = "685fcd55c70c00d47287238952df5e6b" # !!! GERÇEK ve AKTİF API ANAHTARINIZI BURAYA GİRİN !!!
VARSAYILAN_BIRIMLER = "metric"
VARSAYILAN_DIL = "tr"
ONERI_LIMITI = 5
ONBELLEK_TTL_SANIYE = 600 # API yanıtlarını 10 dakika önbellekte tut
ONBELLEK_MAKS_BOYUT = 100

# --- Flask Uygulaması ve Kayıtçı (Logger) Kurulumu ---
uygulama = Flask(__name__)
kayit_bicimlendirici = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
akis_isleyici = logging.StreamHandler(sys.stdout)
akis_isleyici.setFormatter(kayit_bicimlendirici)
uygulama.logger.handlers.clear()
uygulama.logger.addHandler(akis_isleyici)
uygulama.logger.setLevel(logging.INFO)

# --- CORS (Cross-Origin Resource Sharing) ---
CORS(uygulama)

# --- Varlık (Asset) Yolları ---
try:
    temel_yol = os.path.dirname(os.path.abspath(__file__))
except NameError:
    temel_yol = os.getcwd()
VARLIK_YOLU = os.path.join(temel_yol, "assets")
ARKA_PLAN_RESIM_YOLU = os.path.join(VARLIK_YOLU, "gifs")
VARSAYILAN_ARKA_PLAN_RESIM_ADI = "1.jpg"

HAVA_DURUMU_RESIM_ESLESMESI = {
    "clear": "clear.gif", "clouds": "clouds.gif", "rain": "rain.gif",
    "drizzle": "rain1.gif", "thunderstorm": "thunderstorm.jpg", "snow": "snow.gif",
    "mist": "smoke.gif", "smoke": "smoke.gif", "haze": "smoke.gif",
    "dust": "dust.webp", "fog": "fog.jpg", "sand": "dust.webp",
    "ash": "smoke.gif", "squall": "clouds.gif", "tornado": "thunderstorm.jpg",
}

HKI_SEVIYELERI = {
    1: {"seviye": "İyi", "renk": "#A8E05F"}, 2: {"seviye": "Orta", "renk": "#FDD74F"},
    3: {"seviye": "Hassas Gruplar İçin Sağlıksız", "renk": "#FF9B57"},
    4: {"seviye": "Sağlıksız", "renk": "#FE6A69"}, 5: {"seviye": "Çok Sağlıksız", "renk": "#A97ABC"}
}

# --- Önbellekler ---
guncel_hava_durumu_onbellek = TTLCache(maxsize=ONBELLEK_MAKS_BOYUT, ttl=ONBELLEK_TTL_SANIYE)
tahmin_onbellek = TTLCache(maxsize=ONBELLEK_MAKS_BOYUT, ttl=ONBELLEK_TTL_SANIYE)
hki_onbellek = TTLCache(maxsize=ONBELLEK_MAKS_BOYUT, ttl=ONBELLEK_TTL_SANIYE)
geo_onbellek = TTLCache(maxsize=ONBELLEK_MAKS_BOYUT * 2, ttl=ONBELLEK_TTL_SANIYE * 6) # Geo daha uzun süre tutulabilir

# --- API Çağrı Fonksiyonları (Yeniden Yapılandırıldı) ---

# --- Önbellek Anahtar Fonksiyonları ---
def standart_api_onbellek_anahtari(enlem, boylam, api_anahtari, birimler, dil):
    # API anahtarını anahtara dahil etmemek güvenlik açısından daha iyi olabilir,
    # ancak farklı anahtarlar farklı sonuçlar verebilirse dahil edilebilir.
    # Şimdilik dahil etmiyoruz.
    return keys.hashkey(round(enlem, 4), round(boylam, 4), birimler, dil)

def hki_onbellek_anahtari(enlem, boylam, api_anahtari):
     # API anahtarını anahtara dahil etmiyoruz.
     return keys.hashkey(round(enlem, 4), round(boylam, 4))

def geo_onbellek_anahtari(sorgu, api_anahtari, limit, dil):
     # API anahtarını anahtara dahil etmiyoruz.
     return keys.hashkey(sorgu.lower(), limit, dil)

def geo_koordinat_onbellek_anahtari(sehir, api_anahtari, ulke, dil):
     # API anahtarını anahtara dahil etmiyoruz.
     return keys.hashkey(sehir.lower(), ulke.lower(), dil)

# --- Şehir Önerileri ---
@cached(geo_onbellek, key=lambda sorgu, api_anahtari, limit, dil: geo_onbellek_anahtari(sorgu, api_anahtari, limit, dil))
def sehir_onerilerini_getir_api(sorgu, api_anahtari, limit=5, dil=VARSAYILAN_DIL):
    """Verilen sorguya göre OpenWeatherMap Geo API'sinden şehir önerileri alır."""
    if not sorgu or len(sorgu) < 2: return []
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct"
    parametreler = {'q': sorgu, 'limit': limit, 'appid': api_anahtari}
    uygulama.logger.info(f"Şehir öneri isteği: {geo_url} - Parametreler: {parametreler}")
    oneriler = []
    try:
        yanit = requests.get(geo_url, params=parametreler, timeout=5)
        yanit.raise_for_status() # HTTP hatalarında exception fırlat
        veri = yanit.json()
        if veri:
            # Aynı şehir/ülke kombinasyonunu tekrar eklememek için
            benzersiz_oneriler = {}
            for oge in veri:
                benzersiz_anahtar = (oge.get('name', '').lower(), oge.get('country', '').lower())
                # Eğer koordinat bilgisi varsa ve daha önce eklenmemişse ekle
                if benzersiz_anahtar not in benzersiz_oneriler and oge.get('lat') and oge.get('lon'):
                    eyalet = f", {oge.get('state')}" if oge.get('state') else ""
                    ulke_kodu = oge.get('country', '')
                    # İstenen dilde yerel adı al, yoksa varsayılan adı kullan
                    yerel_ad = oge.get('local_names', {}).get(dil, oge.get('name', 'Bilinmeyen'))
                    gorunen_ad = f"{yerel_ad}{eyalet}, {ulke_kodu}"
                    benzersiz_oneriler[benzersiz_anahtar] = {
                        'display': gorunen_ad, 'name': oge.get('name'),
                        'local_name': yerel_ad, 'country': ulke_kodu,
                        'lat': oge.get('lat'), 'lon': oge.get('lon')
                    }
            oneriler = list(benzersiz_oneriler.values())[:limit] # Limite göre kes
            uygulama.logger.info(f"'{sorgu}' için {len(oneriler)} adet şehir önerisi bulundu.")
        else:
            uygulama.logger.info(f"Şehir önerisi bulunamadı: {sorgu}")
    except requests.exceptions.RequestException as e:
        uygulama.logger.error(f"Şehir önerisi API hatası: {e}")
    except Exception as e:
        # Beklenmeyen hataları yakala
        uygulama.logger.error(f"Şehir önerisi işleme hatası: {type(e).__name__}: {e}")
    return oneriler

# --- Koordinat Bulma ---
@cached(geo_onbellek, key=lambda sehir, api_anahtari, ulke, dil: geo_koordinat_onbellek_anahtari(sehir, api_anahtari, ulke, dil))
def koordinatlari_al(sehir, api_anahtari, ulke="", dil=VARSAYILAN_DIL):
    """Verilen şehir ve ülke (isteğe bağlı) için koordinatları bulur."""
    sorgu = f"{sehir},{ulke}" if ulke else sehir
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct"
    parametreler = {'q': sorgu, 'limit': 1, 'appid': api_anahtari}
    uygulama.logger.info(f"Koordinat isteği: {geo_url} - Parametreler: {parametreler}")
    try:
        yanit = requests.get(geo_url, params=parametreler, timeout=10)
        yanit.raise_for_status()
        veri = yanit.json()
        if veri:
            ilk_sonuc = veri[0]
            enlem = ilk_sonuc.get('lat')
            boylam = ilk_sonuc.get('lon')
            bulunan_ulke = ilk_sonuc.get('country', '')
            # Yerel dildeki şehir adını al, yoksa API'nin verdiği adı kullan
            geo_kodlanmis_sehir_adi = ilk_sonuc.get('local_names', {}).get(dil, ilk_sonuc.get('name'))
            if enlem is not None and boylam is not None:
                uygulama.logger.info(f"Koordinatlar bulundu: {geo_kodlanmis_sehir_adi}, {bulunan_ulke} ({enlem}, {boylam})")
                return enlem, boylam, bulunan_ulke, geo_kodlanmis_sehir_adi
            else:
                # Koordinatlar gelmediyse (beklenmedik durum)
                uygulama.logger.warning(f"Koordinat verisi eksik: {sorgu} - Sonuç: {ilk_sonuc}")
                return None, None, None, None
        else:
            uygulama.logger.warning(f"Koordinat bulunamadı: {sorgu}")
            return None, None, None, None
    except requests.exceptions.RequestException as e:
        uygulama.logger.error(f"Koordinat API hatası: {e}")
        return None, None, None, None
    except Exception as e:
        uygulama.logger.error(f"Koordinat işleme hatası: {type(e).__name__}: {e}")
        return None, None, None, None

# --- Mevcut Hava Durumu ---
@cached(guncel_hava_durumu_onbellek, key=standart_api_onbellek_anahtari)
def guncel_hava_durumu_verisi_al(enlem, boylam, api_anahtari, birimler, dil):
    """Mevcut hava durumu verisini /data/2.5/weather endpoint'inden alır."""
    if enlem is None or boylam is None: return None
    hava_durumu_url = f"https://api.openweathermap.org/data/2.5/weather"
    parametreler = {'lat': enlem, 'lon': boylam, 'appid': api_anahtari, 'units': birimler, 'lang': dil}
    uygulama.logger.info(f"Mevcut Hava Durumu API İsteği: {hava_durumu_url} - Parametreler: {parametreler}")
    try:
        yanit = requests.get(hava_durumu_url, params=parametreler, timeout=10)
        yanit.raise_for_status()
        veri = yanit.json()
        uygulama.logger.info(f"Mevcut Hava Durumu verisi başarıyla alındı (enlem={enlem}, boylam={boylam}).")
        return veri
    except requests.exceptions.RequestException as e:
        uygulama.logger.error(f"Mevcut Hava Durumu API Hatası: {e}")
        # Yanıt varsa içeriğini de logla
        if yanit is not None: uygulama.logger.error(f"Yanıt: {yanit.text}")
        return None
    except Exception as e:
        uygulama.logger.error(f"Mevcut Hava Durumu işleme hatası: {type(e).__name__}: {e}")
        return None

# --- 5 Günlük / 3 Saatlik Tahmin ---
@cached(tahmin_onbellek, key=standart_api_onbellek_anahtari)
def tahmin_verisi_al(enlem, boylam, api_anahtari, birimler, dil):
    """5 günlük / 3 saatlik tahmin verisini /data/2.5/forecast endpoint'inden alır."""
    if enlem is None or boylam is None: return None
    tahmin_url = f"https://api.openweathermap.org/data/2.5/forecast"
    parametreler = {'lat': enlem, 'lon': boylam, 'appid': api_anahtari, 'units': birimler, 'lang': dil}
    uygulama.logger.info(f"Tahmin API İsteği: {tahmin_url} - Parametreler: {parametreler}")
    try:
        yanit = requests.get(tahmin_url, params=parametreler, timeout=15)
        yanit.raise_for_status()
        veri = yanit.json()
        uygulama.logger.info(f"Tahmin verisi başarıyla alındı (enlem={enlem}, boylam={boylam}).")
        return veri
    except requests.exceptions.RequestException as e:
        uygulama.logger.error(f"Tahmin API Hatası: {e}")
        if yanit is not None: uygulama.logger.error(f"Yanıt: {yanit.text}")
        return None
    except Exception as e:
        uygulama.logger.error(f"Tahmin işleme hatası: {type(e).__name__}: {e}")
        return None

# --- Hava Kalitesi ---
@cached(hki_onbellek, key=hki_onbellek_anahtari)
def hava_kalitesi_verisi_al(enlem, boylam, api_anahtari):
    """Hava kalitesi verisini alır."""
    if enlem is None or boylam is None: return None
    hki_url = f"http://api.openweathermap.org/data/2.5/air_pollution"
    parametreler = {'lat': enlem, 'lon': boylam, 'appid': api_anahtari}
    uygulama.logger.info(f"Hava Kalitesi API İsteği: {hki_url} - Parametreler: {parametreler}")
    try:
        yanit = requests.get(hki_url, params=parametreler, timeout=10)
        yanit.raise_for_status()
        veri = yanit.json()
        uygulama.logger.info(f"Hava Kalitesi verisi başarıyla alındı (enlem={enlem}, boylam={boylam}).")
        # API yanıtı bir liste içerir, ilk öğeyi alırız
        return veri['list'][0] if veri and 'list' in veri and veri['list'] else None
    except requests.exceptions.RequestException as e:
        uygulama.logger.error(f"Hava Kalitesi API Hatası: {e}")
        if yanit is not None: uygulama.logger.error(f"Yanıt: {yanit.text}")
        return None
    except Exception as e:
        uygulama.logger.error(f"Hava Kalitesi işleme hatası: {type(e).__name__}: {e}")
        return None

# --- Veri İşleme Fonksiyonu (Yeniden Yapılandırıldı) ---
def birlestirilmis_veriyi_isle(guncel_veri, tahmin_veri, hki_veri):
    """Mevcut, tahmin ve HKI verilerini frontend için birleştirir ve işler."""
    # Gerekli veriler yoksa işlem yapma
    if not guncel_veri or not tahmin_veri:
        uygulama.logger.error("birlestirilmis_veriyi_isle: İşlenecek mevcut veya tahmin verisi eksik.")
        return None

    try:
        islenmis = {
            "current": {}, # Mevcut durum
            "hourly": [],  # Saatlik tahmin (ilk 24 saat, 3 saatlik aralıklarla)
            "daily": [],   # Günlük tahmin (5 gün)
            "aqi": None    # Hava Kalitesi İndeksi
        }

        # 1. Mevcut Hava Durumu Bilgileri (/weather'dan)
        # Ana hava durumu (örn: "Clouds", "Rain") ve detaylı açıklama
        mevcut_hava = guncel_veri.get('weather', [{}])[0]
        ana_durum = mevcut_hava.get('main', '').lower() # Küçük harfe çevirerek eşleştirme yap
        arka_plan_resmi = HAVA_DURUMU_RESIM_ESLESMESI.get(ana_durum, VARSAYILAN_ARKA_PLAN_RESIM_ADI) # Eşleşme yoksa varsayılan

        islenmis["current"] = {
            "dt": guncel_veri.get('dt'), # Veri zaman damgası (Unix, UTC)
            "sunrise": guncel_veri.get('sys', {}).get('sunrise'), # Gün doğumu (Unix, UTC)
            "sunset": guncel_veri.get('sys', {}).get('sunset'),   # Gün batımı (Unix, UTC)
            "temp": guncel_veri.get('main', {}).get('temp'), # Sıcaklık
            "feels_like": guncel_veri.get('main', {}).get('feels_like'), # Hissedilen sıcaklık
            "pressure": guncel_veri.get('main', {}).get('pressure'), # Basınç (hPa)
            "humidity": guncel_veri.get('main', {}).get('humidity'), # Nem (%)
            "visibility": guncel_veri.get('visibility'), # Görüş mesafesi (metre)
            "wind_speed": guncel_veri.get('wind', {}).get('speed'), # Rüzgar hızı (metre/sn)
            "wind_deg": guncel_veri.get('wind', {}).get('deg'),   # Rüzgar yönü (derece)
            "desc": mevcut_hava.get('description', '').capitalize(), # Açıklama (ilk harf büyük)
            "icon": mevcut_hava.get('icon', '01d'), # Hava durumu ikonu kodu
            "background_image": arka_plan_resmi, # Belirlenen arka plan resmi
            "temp_min": None, # O günün min sıcaklığı (tahminden alınacak)
            "temp_max": None, # O günün max sıcaklığı (tahminden alınacak)
        }

        # 2. Saatlik (3 Saatlik) Tahmin (/forecast'tan ilk 8 kayıt = 24 saat)
        saatlik_liste = tahmin_veri.get('list', [])
        for oge in saatlik_liste[:8]: # Sadece ilk 8 (24 saat) veriyi al
            saatlik_hava = oge.get('weather', [{}])[0]
            islenmis["hourly"].append({
                'dt': oge.get('dt'), # Zaman damgası
                'temp': oge.get('main', {}).get('temp'), # Sıcaklık
                'icon': saatlik_hava.get('icon', '01d'), # İkon
                'desc': saatlik_hava.get('description', ''), # Açıklama
                # Yağış olasılığı (0-1 arası gelir, 100 ile çarpıp yuvarla)
                'pop': round(oge.get('pop', 0) * 100) if oge.get('pop') is not None else 0
            })

        # 3. Günlük Tahmin (/forecast'tan 5 günlük veri işleme)
        # Her güne ait sıcaklık, ikon ve yağış olasılıklarını toplamak için defaultdict kullan
        gunluk_tahminler = defaultdict(lambda: {'sicakliklar': [], 'ikonlar': [], 'yagis_olasiklari': []})
        # Tahmin listesindeki her bir 3 saatlik periyodu işle
        for oge in saatlik_liste:
            # Zaman damgasını UTC datetime nesnesine çevir
            dt_nesnesi = datetime.fromtimestamp(oge['dt'], tz=timezone.utc)
            # Günü YYYY-AA-GG formatında al (bu, günleri gruplamak için anahtar olacak)
            gun_str = dt_nesnesi.strftime('%Y-%m-%d')
            # O gün için ilgili verileri listelere ekle
            gunluk_tahminler[gun_str]['sicakliklar'].append(oge.get('main', {}).get('temp'))
            gunluk_tahminler[gun_str]['ikonlar'].append(oge.get('weather', [{}])[0].get('icon', '01d'))
            gunluk_tahminler[gun_str]['yagis_olasiklari'].append(round(oge.get('pop', 0) * 100) if oge.get('pop') is not None else 0)

        # Türkçe kısa gün isimleri
        gunler_tr_kisa = {0: "Pzt", 1: "Sal", 2: "Çar", 3: "Per", 4: "Cum", 5: "Cmt", 6: "Paz"}
        bugun_tarih = datetime.now(timezone.utc).date() # Bugünün UTC tarihi
        islenmis_gunluk_sayisi = 0

        # Gruplanmış günlük verileri işle (tarihe göre sıralı olarak)
        for gun_str in sorted(gunluk_tahminler.keys()):
            if islenmis_gunluk_sayisi >= 5: break # En fazla 5 gün göster

            gun_verisi = gunluk_tahminler[gun_str]
            # Eğer o gün için sıcaklık verisi yoksa (beklenmedik durum), atla
            if not gun_verisi['sicakliklar']: continue

            # Gün string'ini date nesnesine çevir
            gun_tarih = datetime.strptime(gun_str, '%Y-%m-%d').date()

            # Gün adını belirle ("Bugün" veya kısa gün adı)
            gun_adi = "Bugün" if gun_tarih == bugun_tarih else gunler_tr_kisa.get(gun_tarih.weekday(), gun_tarih.strftime('%a'))

            # Min/Max sıcaklıkları hesapla
            sicaklik_min = min(gun_verisi['sicakliklar']) if gun_verisi['sicakliklar'] else None
            sicaklik_maks = max(gun_verisi['sicakliklar']) if gun_verisi['sicakliklar'] else None

            # Temsili ikonu belirle (gündüz ikonlarını ('d') tercih et, en sık olanı al)
            gunduz_ikonlari = [ikon for ikon in gun_verisi['ikonlar'] if 'd' in ikon]
            if not gunduz_ikonlari: gunduz_ikonlari = gun_verisi['ikonlar'] # Gündüz yoksa gece ikonlarını kullan
            # En sık tekrarlanan ikonu bul, liste boşsa varsayılanı kullan
            en_yaygin_ikon = max(set(gunduz_ikonlari), key=gunduz_ikonlari.count) if gunduz_ikonlari else '01d'

            # O gün için en yüksek yağış olasılığını al
            maks_yagis_olasiligi = max(gun_verisi['yagis_olasiklari']) if gun_verisi['yagis_olasiklari'] else 0

            # İşlenmiş günlük veriyi listeye ekle
            islenmis["daily"].append({
                'day': gun_adi, # Gün adı (Bugün, Pzt, Sal...)
                'dt': int(datetime.strptime(gun_str + " 12:00:00", '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()), # Günün ortası (öğlen 12) timestamp
                'temp_min': sicaklik_min, # En düşük sıcaklık
                'temp_max': sicaklik_maks, # En yüksek sıcaklık
                'icon': en_yaygin_ikon, # Temsili ikon
                'pop': maks_yagis_olasiligi, # Maksimum yağış olasılığı (%)
                'desc': '' # Günlük genel açıklama bu API'de yok, istenirse ikona göre eklenebilir
            })

            # Eğer işlenen gün bugünün tarihi ise, min/max sıcaklığı ana bölüme de ata
            if gun_tarih == bugun_tarih:
                islenmis["current"]["temp_min"] = sicaklik_min
                islenmis["current"]["temp_max"] = sicaklik_maks

            islenmis_gunluk_sayisi += 1


        # 4. Hava Kalitesi Verisini İşle
        if hki_veri and 'main' in hki_veri:
             hki_indeks = hki_veri['main'].get('aqi') # AQI değeri (1-5)
             if hki_indeks is not None and hki_indeks in HKI_SEVIYELERI:
                 hki_bilgi = HKI_SEVIYELERI[hki_indeks] # İndekse karşılık gelen seviye ve renk
                 islenmis["aqi"] = {
                     "index": hki_indeks,
                     "level": hki_bilgi["seviye"], # Seviye adı (İyi, Orta...)
                     "color": hki_bilgi["renk"],   # Seviyeye karşılık gelen renk kodu
                     "components": hki_veri.get('components', {}) # Kirletici bileşenlerin detayları
                 }
             else:
                  uygulama.logger.warning(f"HKI verisinde beklenen indeks ({hki_indeks}) bulunamadı veya geçersiz.")
        else:
             uygulama.logger.info("Geçerli HKI verisi bulunamadı veya işlenemedi.")

        uygulama.logger.info("API verileri başarıyla işlendi ve birleştirildi.")
        return islenmis

    except KeyError as ke:
        # Veri yapısında beklenmedik bir anahtar eksikse hata logla
        uygulama.logger.exception(f"!!! Veri işlenirken anahtar hatası: {ke}")
        return None
    except Exception as e:
        # Diğer tüm beklenmedik hataları logla
        uygulama.logger.exception(f"!!! Veri işlenirken genel hata oluştu: {e}")
        return None

# --- Flask Rotaları ---

@uygulama.route('/suggestions')
def onerileri_getir_rota():
    """Şehir adı sorgusuna göre önerileri JSON formatında döndürür."""
    sorgu = request.args.get('q') # URL'den 'q' parametresini al (örn: /suggestions?q=ista)
    dil = request.args.get('lang', VARSAYILAN_DIL) # Dil parametresi, varsayılan 'tr'
    if not sorgu: return jsonify([]) # Sorgu boşsa boş liste döndür
    # API anahtarı kontrolü
    if not API_ANAHTARI or len(API_ANAHTARI) < 30:
         uygulama.logger.error("API Anahtarı eksik veya geçersiz.")
         return jsonify({"error": "Servis yapılandırma hatası."}), 500
    # API çağrısını yap (önbellek kontrolü içeride yapılır)
    oneriler = sehir_onerilerini_getir_api(sorgu, API_ANAHTARI, ONERI_LIMITI, dil)
    return jsonify(oneriler) # Sonuçları JSON olarak döndür

@uygulama.route('/weather')
def hava_durumu_getir_rota():
    """Belirtilen şehir veya koordinatlar için birleştirilmiş hava durumu verilerini döndürür."""
    # URL parametrelerini al
    sehir = request.args.get('city')
    ulke = request.args.get('country', '') # Ülke kodu isteğe bağlı
    enlem_str = request.args.get('lat')
    boylam_str = request.args.get('lon')
    birimler = request.args.get('units', VARSAYILAN_BIRIMLER)
    dil = request.args.get('lang', VARSAYILAN_DIL)

    uygulama.logger.info(f"Hava durumu isteği alındı: sehir={sehir}, ulke={ulke}, enlem={enlem_str}, boylam={boylam_str}, birimler={birimler}, dil={dil}")

    # API anahtarı var mı ve geçerli görünüyor mu diye kontrol et
    if not API_ANAHTARI or API_ANAHTARI == "YOUR_OPENWEATHERMAP_API_KEY" or len(API_ANAHTARI) < 30:
         uygulama.logger.error("API Anahtarı eksik veya geçersiz.")
         # Kullanıcıya API anahtarı sorunu olduğunu belirten bir hata döndür (503 Service Unavailable)
         return jsonify({"success": False, "message": "Servis API anahtarı sorunu nedeniyle kullanılamıyor."}), 503

    enlem, boylam, bulunan_ulke, geo_kodlanmis_sehir_adi = None, None, ulke, sehir

    # Koordinatları Belirle: Öncelik enlem/boylam parametrelerine verilir
    if enlem_str and boylam_str:
        try:
            enlem = float(enlem_str)
            boylam = float(boylam_str)
            # Koordinat varsa, şehir adı sadece gösterim için kullanılır (varsa)
            geo_kodlanmis_sehir_adi = sehir if sehir else f"Konum ({enlem:.3f}, {boylam:.3f})"
            bulunan_ulke = ulke
            uygulama.logger.info(f"Koordinatlarla devam ediliyor: enlem={enlem}, boylam={boylam}")
        except ValueError:
            # Geçersiz sayı formatı varsa hata döndür
            uygulama.logger.warning(f"Geçersiz enlem/boylam parametreleri: {enlem_str}, {boylam_str}")
            return jsonify({"success": False, "message": "Geçersiz koordinat formatı."}), 400
    elif sehir:
        # Enlem/boylam yok ama şehir adı varsa, koordinatları bulmaya çalış
        uygulama.logger.info(f"Şehir adıyla koordinatlar aranıyor: {sehir}, {ulke}")
        enlem, boylam, bulunan_ulke_kodu, sehir_adi_geo_dan = koordinatlari_al(sehir, API_ANAHTARI, ulke, dil)
        if enlem is None or boylam is None:
            # Koordinatlar bulunamazsa 404 hatası döndür
            uygulama.logger.warning(f"Şehir için koordinat bulunamadı: {sehir}, {ulke}")
            return jsonify({"success": False, "message": f"'{sehir}' şehri bulunamadı."}), 404
        # Geo API'den dönen adı ve ülke kodunu kullan
        geo_kodlanmis_sehir_adi = sehir_adi_geo_dan
        bulunan_ulke = bulunan_ulke_kodu
        uygulama.logger.info(f"Koordinatlar bulundu: {geo_kodlanmis_sehir_adi}, {bulunan_ulke} ({enlem}, {boylam})")
    else:
        # Ne koordinat ne de şehir adı varsa, istek geçersizdir
        uygulama.logger.warning("İstekte şehir veya koordinat belirtilmedi.")
        return jsonify({"success": False, "message": "Lütfen bir şehir adı veya koordinat belirtin."}), 400

    # --- Ayrı API'lerden Verileri Al (Önbellek kontrolü fonksiyon içlerinde) ---
    uygulama.logger.info(f"Mevcut hava durumu verisi isteniyor...")
    guncel_veri = guncel_hava_durumu_verisi_al(enlem, boylam, API_ANAHTARI, birimler, dil)
    if not guncel_veri:
        # Mevcut hava durumu verisi alınamazsa kritik hata
        uygulama.logger.error(f"!!! hava_durumu_getir_rota: Mevcut hava durumu verisi alınamadı.")
        return jsonify({"success": False, "message": "Mevcut hava durumu bilgisi alınamadı. API anahtarınızı veya bağlantınızı kontrol edin."}), 500

    uygulama.logger.info(f"Tahmin verisi isteniyor...")
    tahmin_veri = tahmin_verisi_al(enlem, boylam, API_ANAHTARI, birimler, dil)
    if not tahmin_veri:
        # Tahmin verisi alınamazsa kritik hata
        uygulama.logger.error(f"!!! hava_durumu_getir_rota: Tahmin verisi alınamadı.")
        return jsonify({"success": False, "message": "Tahmin bilgisi alınamadı. API anahtarınızı veya bağlantınızı kontrol edin."}), 500

    uygulama.logger.info(f"Hava Kalitesi verisi isteniyor...")
    hki_veri = hava_kalitesi_verisi_al(enlem, boylam, API_ANAHTARI)
    if not hki_veri:
         # HKI verisi alınamazsa sadece uyarı verilir, işlem devam eder
         uygulama.logger.warning(f"Hava kalitesi verisi alınamadı veya geçersiz.")

    # --- Verileri İşle ve Birleştir ---
    uygulama.logger.info("Alınan API verileri işleniyor ve birleştiriliyor...")
    islenmis_veri = birlestirilmis_veriyi_isle(guncel_veri, tahmin_veri, hki_veri)
    if not islenmis_veri:
        # Veri işleme sırasında hata oluşursa 500 hatası döndür
        uygulama.logger.error(f"!!! hava_durumu_getir_rota: birlestirilmis_veriyi_isle None döndürdü.")
        return jsonify({"success": False, "message": "Hava durumu verileri işlenirken bir sorun oluştu."}), 500

    # Başarılı yanıtı oluştur
    sonuc = {
        "success": True,
        "city": { # Şehir bilgileri
            "name": geo_kodlanmis_sehir_adi,
            "country": bulunan_ulke,
            "lat": enlem,
            "lon": boylam
        },
        **islenmis_veri # İşlenmiş current, hourly, daily, aqi verilerini ekle
    }

    uygulama.logger.info(f"Başarılı yanıt gönderiliyor: {geo_kodlanmis_sehir_adi}, {bulunan_ulke}")
    return jsonify(sonuc) # Sonucu JSON olarak döndür

@uygulama.route('/')
def indeks():
    """Ana endpoint, API'nin çalıştığını doğrulamak için."""
    uygulama.logger.info("Ana endpoint '/' çağrıldı.")
    return jsonify({"message": "Hava Durumu API (Standart Endpoints) başarıyla çalışıyor.", "status": "ok"})

# --- Sunucu Başlatma ---
if __name__ == '__main__':
    # Uygulama başlamadan önce API anahtarının varlığını tekrar kontrol et
    if not API_ANAHTARI or API_ANAHTARI == "YOUR_OPENWEATHERMAP_API_KEY" or len(API_ANAHTARI) < 30:
        uygulama.logger.critical("-" * 60)
        uygulama.logger.critical("!!! KRİTİK HATA: Geçerli bir OpenWeatherMap API anahtarı 'API_ANAHTARI' değişkenine girilmelidir! arka_uc.py dosyasını düzenleyin.")
        uygulama.logger.critical("-" * 60)
        sys.exit(1) # Hata durumunda uygulamayı sonlandır

    # Sunucu portunu ortam değişkeninden al, yoksa 5000 kullan
    port = int(os.environ.get("PORT", 5000))
    # Hata ayıklama modunu ortam değişkenlerinden kontrol et
    hata_ayiklama_modu = os.environ.get("FLASK_ENV", "production").lower() == "development" or \
                         os.environ.get("DEBUG", "false").lower() in ["true", "1"]

    uygulama.logger.info(f"Flask sunucusu 0.0.0.0:{port} üzerinde başlatılıyor...")
    uygulama.logger.info(f"Kullanılan API Endpoints: /weather, /forecast, /air_pollution (içsel olarak)")
    uygulama.logger.info(f"Hata Ayıklama Modu: {'Aktif' if hata_ayiklama_modu else 'Pasif'}")
    uygulama.logger.info(f"Önbellek Süresi: {ONBELLEK_TTL_SANIYE} saniye")
    uygulama.logger.info(f"Varsayılan Dil: {VARSAYILAN_DIL}, Varsayılan Birim: {VARSAYILAN_BIRIMLER}")
    try:
        # Sunucuyu başlat (debug modu aktifse otomatik yeniden yükleme de aktif olur)
        uygulama.run(host='0.0.0.0', port=port, debug=hata_ayiklama_modu, use_reloader=hata_ayiklama_modu)
    except Exception as e:
        # Sunucu başlatılamazsa kritik hata logla ve çık
        uygulama.logger.critical(f"Sunucu başlatılırken kritik hata: {e}")
        sys.exit(1)