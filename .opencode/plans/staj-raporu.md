# Plan: Staj Raporu (.docx) Üretimi

## Durum
- `rag_llm` projesi detaylıca incelendi (tüm modüller, file:line referansları)
- `StajRaporuDuzeni.pdf` metni çıkarıldı ve biçim kuralları belirlendi
- Kullanıcı `.docx` formatını seçti
- python-docx 1.1.2 mevcut

## Hedef Deliverable
`Staj_Raporu.docx` — `StajRaporuDuzeni.pdf` kurallarına tam uyumlu:

### Biçim Kuralları (PDF'den)
- Font: Arial 12pt
- Kenar boşlukları: üst/sol 4.0 cm, alt/sağ 2.5 cm
- Satır aralığı: 1.5
- Ana başlık: BÜYÜK HARF + koyu (örn "1. GİRİŞ")
- Alt başlık: Her Sözcüğün İlk Harfi Büyük + koyu (örn "3.5.1. Tanımlanan Araçlar")
- Numara: 1. / 1.1 / 2.1.1 (3 seviye), sonra a) b) c)
- En az 6 sayfa (kapak + içindekiler hariç)
- Kapak ve içindekiler hariç sayfa numarası 1,2,3...

### Bölümler
1. **Kapak Sayfası** — bilinmeyen alanlar (ad, sınıf, numara, tarih, kurum) boş noktalı yer tutucu ile
2. **İçindekiler** — aşağıdaki bölümlere göre otomatik doldurulur
3. **Giriş** — RAG proje konusu, amacı, yapılan çalışma özeti, sonuç
4. **Kurum Tanıtımı** — boş bırakılmış yer tutucu (kullanıcı kurumu dolduracak)
5. **Staj Süreci** (detaylı, çok alt başlıklı):
   - 5.1 Proje Konusu ve Genel Mimari
   - 5.2 Kullanılan Teknolojiler (tablo)
   - 5.3 AST Tabanlı Kod Parçalama (splitters) — file:line ref + kod parçası
   - 5.4 Qdrant Vektör Veritabanı İndeksleme Hattı
   - 5.5 LangChain / LangGraph Ajan Mimarisi
     - 5.5.1 Tanımlanan Araçlar
     - 5.5.2 Sistem Komutlandırması
     - 5.5.3 Bellek ve Denetim Noktası
   - 5.6 Streamlit Web Arayüzü
     - 5.6.1 Oturum Yönetimi ve Diskte Süreklilik
     - 5.6.2 Dosya Paneli ve Tam Ekran
   - 5.7 Uzun Vadeli Bellek: Compaction Mekanizması
   - 5.8 Token Takibi
6. **Sonuç** — kazanılan deneyim, katkılar, sorunlar/gözlemler, teknik öneriler (4.1)
7. **Kaynaklar** — kullanılan gerçek teknolojiler (qdrant, langchain, ollama, tree-sitter, streamlit, vb.)

## Uygulama Yöntemi
`generate_report.py` scripti (python-docx):
- `Document()` oluştur, section margin ayarla (Cm)
- "Normal" stiline Arial 12pt + 1.5 line spacing + eastAsia/cs font zorla
- Yardımcı fonksiyonlar: `ana_baslik`, `alt_baslik`, `paragraf`, `madde`, `ara`
- Her bölüm fonksiyonu (kapak/giris/.../kaynaklar) içerik ekler
- Save → `Staj_Raporu.docx`
- Çalıştır: `python3 generate_report.py`

## İçerik Kaynakları (file:line referansları raporda kullanılacak)
- splitters/text_splitters.py:11-15, 18-37, 40-83, 86-115, 118-154
- qdrant_pipeline/qdrant_main.py:14-18, 25-80, 48-56, 59-63, 66-77
- local_llm/agent.py:46-67, 75-126, 130-216, 242-249, 311
- interface/app.py:48-110, 113-136, 140-148, 196-270, 290-329, 331-373, 451-462, 496, 530-622
- prompts/prompts2.py:2-30
- compaction.md (template)
- token_tracker/base_callback_handler.py:1-17

## Onay Bekleyenler
- Plan modundayım; kullanıcı onayıyla birlikte `generate_report.py` yazılacak ve çalıştırılıp `Staj_Raporu.docx` üretilecek.