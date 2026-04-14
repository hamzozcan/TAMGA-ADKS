# Raspberry Pi 16x2 I2C LCD Durum Ekrani

TAMGA-ADKS icin 4 pinli `16x2 I2C LCD` baglantisi ve durum gosterimi.

## 1. 4 pin LCD baglantisi

Tipik backpack pinleri:

| LCD | Raspberry Pi | Fiziksel pin |
|---|---|---|
| `GND` | `GND` | `Pin 6` |
| `VCC` | `5V` | `Pin 2` veya `Pin 4` |
| `SDA` | `GPIO2 / SDA1` | `Pin 3` |
| `SCL` | `GPIO3 / SCL1` | `Pin 5` |

## 2. Ekranda ne gosterilir

1. satir sabit:

```text
TAMGA-ADKS
```

2. satir backend'den okunur:

- `T` = toplam kayit
- `Y` = yesil
- `S` = sari
- `K` = kirmizi
- `H` = siyah

Ornek veri metni:

```text
T:27 Y:8 S:10 K:6 H:3
```

Bu metin 16 karaktere sigmazsa LCD alt satirda otomatik kaydirilir.

## 3. Onemli not

Ucuz `PCF8574` backpack kartlarinda `SDA/SCL` hatlari bazen `VCC`'ye pull-up edilir.
Raspberry Pi'nin I2C mantik seviyesi `3.3V` oldugu icin, en temiz cozum:

- `3.3V uyumlu backpack` kullanmak
- veya `I2C level shifter` kullanmak
- veya modulu olcup/dogrulayip baglamak

## 4. I2C acma ve adres kontrolu

```bash
sudo raspi-config nonint do_i2c 0
sudo apt install i2c-tools python3-smbus -y
sudo i2cdetect -y 1
```

Yaygin adresler:

- `0x27`
- `0x3F`

## 5. Script

Dosya:

- `donanim/rpi_i2c_16x2_clock.py`

Calistirma:

```bash
cd /home/elliot/Masaüstü/TAMGA-ADKS
python3 donanim/rpi_i2c_16x2_clock.py --address 0x27
```

## 6. Veri kaynagi

Varsayilan olarak script su endpoint'i okur:

```text
http://127.0.0.1:8000/api/stats
```

Yani TAMGA backend acik oldugunda LCD verileri otomatik guncellenir.

## 7. Sorun olursa

1. `sudo i2cdetect -y 1` ile adresi kontrol et.
2. `VCC/GND` ters bagli olmasin.
3. `SDA` kesinlikle `Pin 3`, `SCL` kesinlikle `Pin 5` olsun.
4. Backend kapaliysa alt satir `VERI BEKLENIYOR` olarak kalir.
