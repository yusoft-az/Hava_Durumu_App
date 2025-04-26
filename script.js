document.addEventListener('DOMContentLoaded', () => {
    const sehirGirdisi = document.getElementById('sehir-girdisi');
    const aramaButonu = document.getElementById('arama-butonu');
    const oneriListesi = document.getElementById('oneri-listesi');
    const sehirAdiElementi = document.getElementById('sehir-adi');
    const guncelSicaklikElementi = document.getElementById('guncel-sicaklik');
    const guncelIkonElementi = document.getElementById('guncel-ikon');
    const guncelAciklamaElementi = document.getElementById('guncel-aciklama');
    const minMaksSicaklikElementi = document.getElementById('min-maks-sicaklik');
    const saatlikOgelerKonteyneri = document.getElementById('saatlik-ogeler-konteyneri');
    const gunlukOgelerKonteyneri = document.getElementById('gunluk-ogeler-konteyneri');
    const hataMesajiElementi = document.getElementById('hata-mesaji');
    const guncelBilgiAlani = document.getElementById('guncel-bilgi-alani');
    const saatlikBlok = document.getElementById('saatlik-tahmin-blogu');
    const gunlukBlok = document.getElementById('gunluk-tahmin-blogu');

    const hissedilenElementi = document.getElementById('hissedilen-deger');
    const nemElementi = document.getElementById('nem-deger');
    const ruzgarElementi = document.getElementById('ruzgar-deger');
    const gorusMesafesiElementi = document.getElementById('gorus-mesafesi-deger');
    const gunDogumuElementi = document.getElementById('gun-dogumu-deger');
    const gunBatimiElementi = document.getElementById('gun-batimi-deger');
    const basincElementi = document.getElementById('basinc-deger');
    const hkiElementi = document.getElementById('hki-deger');
    const hkiKonteyneri = document.getElementById('hki-konteyneri');

    const API_TEMEL_URL = "http://localhost:5000";
    let oneriBekletmeZamanlayici;
    const BEKLETME_GECIKMESI = 350;
    const ARKA_PLAN_TEMEL_YOLU = "assets/gifs/";
    const VARSAYILAN_ARKA_PLAN_ADI = "1.jpg";

    function zamaniBicimlendir(zamanDamgasi, saatDilimiOfsetiSaniye = null) {
        if (!zamanDamgasi) return '--:--';
        const tarih = new Date(zamanDamgasi * 1000);
        return tarih.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', hour12: false });
    }

    function ruzgarDerecesiniYoneCevir(derece) {
        if (derece === null || derece === undefined) return '';
        const yonler = ['K', 'KKD', 'KD', 'DKD', 'D', 'DGD', 'GD', 'GGD', 'G', 'GGB', 'GB', 'BGB', 'B', 'BKB', 'KB', 'KKB'];
        const indeks = Math.round(derece / 22.5) % 16;
        return yonler[indeks];
    }

    function gorusMesafesiniBicimlendir(metre) {
        if (metre === null || metre === undefined) return '--';
        if (metre >= 10000) return '> 10 km';
        if (metre >= 1000) {
            return `${(metre / 1000).toFixed(1)} km`;
        }
        return `${metre} m`;
    }

    function basinciBicimlendir(hpa) {
        if (hpa === null || hpa === undefined) return '--';
        return `${hpa}<span class="birim">hPa</span>`;
    }

    function yuklemeGostergesiOlustur() {
        return `
            <div class="yukleniyor-gostergesi">
                <div class="donen-cark"></div>
                <span>Yükleniyor...</span>
            </div>
        `;
    }

    async function havaDurumuGetir(sehir = null, ulke = '', enlem = null, boylam = null) {
        hatayiGizle();
        yukleniyorYerTutuculariGoster();
        oneriListesi.style.display = 'none';

        let url = `${API_TEMEL_URL}/weather?`;
        const parametreler = new URLSearchParams();
        if (enlem !== null && boylam !== null) {
            parametreler.append('lat', enlem);
            parametreler.append('lon', boylam);
            if (sehir) parametreler.append('city', sehir);
            if (ulke) parametreler.append('country', ulke);
        } else if (sehir) {
            parametreler.append('city', sehir);
            if (ulke) parametreler.append('country', ulke);
        } else {
            hataGoster("Şehir adı veya koordinat belirtilmedi.");
            arayuzuTemizle(false);
            yukleniyorYerTutuculariGizle();
            return;
        }
        url += parametreler.toString();

        console.log("İstek URL:", url);

        try {
            const yanit = await fetch(url);
            const veri = await yanit.json();

            if (!yanit.ok) {
                throw new Error(veri.message || `Sunucu hatası (${yanit.status})`);
            }

            if (veri.success) {
                arayuzuGuncelle(veri);
            } else {
                throw new Error(veri.message || "Bilinmeyen bir API hatası oluştu.");
            }
        } catch (hata) {
            console.error("Hava durumu alınırken hata:", hata);
            hataGoster(`Hata: ${hata.message}`);
            arayuzuTemizle(false);
            yukleniyorYerTutuculariGizle();
        }
    }

    function arayuzuGuncelle(veri) {
        hatayiGizle();

        const arkaPlanResimAdi = veri.current?.background_image || VARSAYILAN_ARKA_PLAN_ADI;
        document.body.style.backgroundImage = `url('${ARKA_PLAN_TEMEL_YOLU}${arkaPlanResimAdi}')`;

        sehirAdiElementi.textContent = `${veri.city?.name || 'Bilinmeyen Şehir'}${veri.city?.country ? ', ' + veri.city.country : ''}`;
        guncelSicaklikElementi.textContent = veri.current?.temp !== null ? `${Math.round(veri.current.temp)}°` : '--°';
        guncelAciklamaElementi.textContent = veri.current?.desc || '---';
        minMaksSicaklikElementi.textContent = (veri.current?.temp_min !== null && veri.current?.temp_max !== null)
            ? `↓ ${Math.round(veri.current.temp_min)}°   ↑ ${Math.round(veri.current.temp_max)}°`
            : '↓ --°   ↑ --°';

        if (veri.current?.icon) {
            guncelIkonElementi.src = `https://openweathermap.org/img/wn/${veri.current.icon}@4x.png`;
            guncelIkonElementi.alt = veri.current?.desc || 'Hava durumu ikonu';
            guncelIkonElementi.style.display = 'block';
        } else {
            guncelIkonElementi.style.display = 'none';
        }

        if (hissedilenElementi) hissedilenElementi.innerHTML = veri.current?.feels_like !== null ? `${Math.round(veri.current.feels_like)}<span class="birim">°C</span>` : '--';
        if (nemElementi) nemElementi.innerHTML = veri.current?.humidity !== null ? `${veri.current.humidity}<span class="birim">%</span>` : '--';
        if (ruzgarElementi) {
            const hiz_mps = veri.current?.wind_speed;
            const hiz_kmh = hiz_mps !== null ? Math.round(hiz_mps * 3.6) : '--';
            const yon = ruzgarDerecesiniYoneCevir(veri.current?.wind_deg);
            ruzgarElementi.innerHTML = `${hiz_kmh}<span class="birim">km/h</span> ${yon}`;
        }
        if (gorusMesafesiElementi) gorusMesafesiElementi.textContent = gorusMesafesiniBicimlendir(veri.current?.visibility) || '--';
        if (basincElementi) basincElementi.innerHTML = basinciBicimlendir(veri.current?.pressure) || '--';
        if (gunDogumuElementi) gunDogumuElementi.textContent = zamaniBicimlendir(veri.current?.sunrise) || '--:--';
        if (gunBatimiElementi) gunBatimiElementi.textContent = zamaniBicimlendir(veri.current?.sunset) || '--:--';

        if (hkiKonteyneri && hkiElementi) {
             if (veri.aqi) {
                 hkiElementi.textContent = `${veri.aqi.level} (${veri.aqi.index})`;
                 hkiElementi.style.backgroundColor = veri.aqi.color || 'transparent';
                 hkiElementi.style.color = (veri.aqi.color === '#FDD74F' || veri.aqi.color === '#A8E05F') ? '#333' : '#fff';
                 hkiKonteyneri.style.display = 'flex';
             } else {
                 hkiKonteyneri.style.display = 'none';
             }
        }

        saatlikOgelerKonteyneri.innerHTML = '';
        if (veri.hourly && veri.hourly.length > 0) {
            veri.hourly.forEach(saat => {
                const yagisSans = saat.pop !== null ? Math.round(saat.pop) : 0;
                const saatlikOgeHTML = `
                    <div class="saatlik-oge">
                        <span class="zaman">${zamaniBicimlendir(saat.dt) || '--:--'}</span>
                        <img src="https://openweathermap.org/img/wn/${saat.icon || '01d'}@2x.png" alt="${saat.desc || ''}">
                        <span class="sicaklik">${saat.temp !== null ? Math.round(saat.temp) + '°' : '--°'}</span>
                        ${yagisSans > 10 ? `<span class="yagis-olas" title="Yağış Olasılığı">${yagisSans}%</span>` : ''}
                    </div>`;
                saatlikOgelerKonteyneri.innerHTML += saatlikOgeHTML;
            });
        } else {
            saatlikOgelerKonteyneri.innerHTML = '<div class="yukleniyor-yer-tutucu">Saatlik veri yok</div>';
        }

        gunlukOgelerKonteyneri.innerHTML = '';
        if (veri.daily && veri.daily.length > 0) {
            veri.daily.forEach(gun => {
                const gunlukOgeHTML = `
                    <div class="gunluk-oge">
                        <span class="gun">${gun.day || '---'}</span>
                        <img src="https://openweathermap.org/img/wn/${gun.icon || '01d'}@2x.png" alt="${gun.desc || ''}" title="${gun.desc || ''}">
                        <span class="sicaklik-min" title="En Düşük">${gun.temp_min !== null ? Math.round(gun.temp_min) + '°' : '--°'}</span>
                        <span class="sicaklik-maks" title="En Yüksek">${gun.temp_max !== null ? Math.round(gun.temp_max) + '°' : '--°'}</span>
                    </div>`;
                gunlukOgelerKonteyneri.innerHTML += gunlukOgeHTML;
            });
        } else {
            gunlukOgelerKonteyneri.innerHTML = '<div class="yukleniyor-yer-tutucu">Günlük veri yok</div>';
        }

        guncelBilgiAlani.style.display = 'block';
        saatlikBlok.style.display = 'block';
        gunlukBlok.style.display = 'block';
    }

    async function onerileriGetir(sorgu) {
        if (sorgu.length < 2) {
            oneriListesi.innerHTML = '';
            oneriListesi.style.display = 'none';
            return;
        }
        try {
            const yanit = await fetch(`${API_TEMEL_URL}/suggestions?q=${encodeURIComponent(sorgu)}`);
            if (!yanit.ok) throw new Error('Öneriler alınamadı.');
            const oneriler = await yanit.json();
            onerileriGoster(oneriler);
        } catch (hata) {
            console.error("Öneri hatası:", hata);
            oneriListesi.innerHTML = '';
            oneriListesi.style.display = 'none';
        }
    }

    function onerileriGoster(oneriler) {
        oneriListesi.innerHTML = '';
        if (!oneriler || oneriler.length === 0) {
            oneriListesi.style.display = 'none';
            return;
        }
        oneriler.forEach(oneri => {
            const ogeDiv = document.createElement('div');
            ogeDiv.classList.add('oneri-ogesi');
            ogeDiv.textContent = oneri.display;
            ogeDiv.addEventListener('click', () => {
                sehirGirdisi.value = oneri.name;
                oneriListesi.innerHTML = '';
                oneriListesi.style.display = 'none';
                havaDurumuGetir(oneri.name, oneri.country, oneri.lat, oneri.lon);
            });
            oneriListesi.appendChild(ogeDiv);
        });
        oneriListesi.style.display = 'block';
    }

    function beklet(fonk, gecikme) {
        clearTimeout(oneriBekletmeZamanlayici);
        oneriBekletmeZamanlayici = setTimeout(fonk, gecikme);
    }

    function hataGoster(mesaj) {
        hataMesajiElementi.textContent = mesaj;
        hataMesajiElementi.style.display = 'block';
        yukleniyorYerTutuculariGizle();
    }
    function hatayiGizle() {
        hataMesajiElementi.textContent = '';
        hataMesajiElementi.style.display = 'none';
    }

    function arayuzuTemizle(arkaPlaniSifirla = true) {
        sehirAdiElementi.textContent = '--';
        guncelSicaklikElementi.textContent = '--°';
        guncelIkonElementi.style.display = 'none';
        guncelAciklamaElementi.textContent = '---';
        minMaksSicaklikElementi.textContent = '↓ --°   ↑ --°';

        if (hissedilenElementi) hissedilenElementi.textContent = '--';
        if (nemElementi) nemElementi.textContent = '--';
        if (ruzgarElementi) ruzgarElementi.textContent = '--';
        if (gorusMesafesiElementi) gorusMesafesiElementi.textContent = '--';
        if (basincElementi) basincElementi.textContent = '--';
        if (gunDogumuElementi) gunDogumuElementi.textContent = '--:--';
        if (gunBatimiElementi) gunBatimiElementi.textContent = '--:--';
        if (hkiKonteyneri) hkiKonteyneri.style.display = 'none';
        if (hkiElementi) hkiElementi.textContent = '--';

        guncelBilgiAlani.style.display = 'none';
        saatlikBlok.style.display = 'none';
        gunlukBlok.style.display = 'none';
        saatlikOgelerKonteyneri.innerHTML = '';
        gunlukOgelerKonteyneri.innerHTML = '';

        if (arkaPlaniSifirla) {
            document.body.style.backgroundImage = `url('${ARKA_PLAN_TEMEL_YOLU}${VARSAYILAN_ARKA_PLAN_ADI}')`;
        }
    }

    function yukleniyorYerTutuculariGoster() {
        arayuzuTemizle(false);
        guncelBilgiAlani.style.display = 'block';
        sehirAdiElementi.textContent = 'Yükleniyor...';

        saatlikOgelerKonteyneri.innerHTML = yuklemeGostergesiOlustur();
        gunlukOgelerKonteyneri.innerHTML = yuklemeGostergesiOlustur();

        saatlikBlok.style.display = 'block';
        gunlukBlok.style.display = 'block';
    }

    function yukleniyorYerTutuculariGizle() {
        if(saatlikOgelerKonteyneri.querySelector('.yukleniyor-gostergesi')) {
            saatlikOgelerKonteyneri.innerHTML = '';
        }
         if(gunlukOgelerKonteyneri.querySelector('.yukleniyor-gostergesi')) {
            gunlukOgelerKonteyneri.innerHTML = '';
        }
    }

    aramaButonu.addEventListener('click', () => {
        const sehir = sehirGirdisi.value.trim();
        if (sehir) {
            havaDurumuGetir(sehir);
        } else {
            hataGoster("Lütfen bir şehir adı girin.");
            arayuzuTemizle(false);
        }
        oneriListesi.style.display = 'none';
        sehirGirdisi.blur();
    });

    sehirGirdisi.addEventListener('keypress', (olay) => {
        if (olay.key === 'Enter') {
            aramaButonu.click();
        }
    });

    sehirGirdisi.addEventListener('input', () => {
        const sorgu = sehirGirdisi.value.trim();
        beklet(() => onerileriGetir(sorgu), BEKLETME_GECIKMESI);
    });

    sehirGirdisi.addEventListener('blur', () => {
        setTimeout(() => {
            if (!oneriListesi.matches(':hover')) {
                oneriListesi.style.display = 'none';
            }
        }, 200);
    });

    document.addEventListener('click', (olay) => {
        if (!sehirGirdisi.contains(olay.target) && !oneriListesi.contains(olay.target) && !aramaButonu.contains(olay.target)) {
            oneriListesi.style.display = 'none';
        }
    });

    function baslangicKonumunuAlVeGetir() {
        yukleniyorYerTutuculariGoster();
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (konum) => {
                    const { latitude: enlem, longitude: boylam } = konum.coords;
                    console.log(`Konum alındı: ${enlem}, ${boylam}. Hava durumu getiriliyor...`);
                    havaDurumuGetir(null, '', enlem, boylam);
                },
                (hata) => {
                    console.warn("Konum alınamadı:", hata.message, ". Varsayılan şehir (Ankara) kullanılıyor.");
                     hataGoster("Konum alınamadı. Varsayılan şehir gösteriliyor.");
                    havaDurumuGetir("Ankara");
                },
                { timeout: 8000 }
            );
        } else {
            console.log("Tarayıcı konum servisini desteklemiyor. Varsayılan şehir (Ankara) kullanılıyor.");
             hataGoster("Konum servisi desteklenmiyor. Varsayılan şehir gösteriliyor.");
            havaDurumuGetir("Ankara");
        }
    }

     baslangicKonumunuAlVeGetir();

});