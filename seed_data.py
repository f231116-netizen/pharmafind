"""Demo data for PharmaFind.

IMPORTANT: pharmacy names, addresses, phone numbers, prices and stock levels
are invented for the demo. Medicine ingredients and general uses are the
standard, widely documented ones, but before the showcase, double-check each
entry against the product leaflet (or a pharmacist) and add the medicines
that are actually common in Sulaymaniyah pharmacies.
"""

# (name, address, lat, lng, open_hours, is_24h)
# Coordinates are spread around central Sulaymaniyah (approx. 35.56 N, 45.43 E).
PHARMACIES = [
    ("Shifa Pharmacy",        "Salim Street",            35.5617, 45.4329, "08:00-23:00", False),
    ("Hayat Pharmacy",        "Mawlawi Street",          35.5585, 45.4362, "08:00-22:00", False),
    ("Nawroz Pharmacy",       "Sarchinar Road",          35.5702, 45.3951, "09:00-23:00", False),
    ("Bakhtiari Pharmacy",    "Bakhtiari District",      35.5543, 45.4231, "00:00-24:00", True),
    ("Azadi Pharmacy",        "Azadi Park area",         35.5651, 45.4398, "08:00-22:00", False),
    ("Goizha Pharmacy",       "Goizha Road",             35.5743, 45.4486, "09:00-21:00", False),
    ("Raparin Pharmacy",      "Raparin District",        35.5498, 45.4433, "08:00-23:00", False),
    ("Kani Pharmacy",         "Kani Askan",              35.5689, 45.4157, "08:00-22:00", False),
    ("Malkandi Pharmacy",     "Malkandi District",       35.5521, 45.4074, "08:00-22:00", False),
    ("Tooy Malik Pharmacy",   "Tooy Malik",              35.5755, 45.4302, "09:00-23:00", False),
    ("Hospital Road Pharmacy","Near Shar Hospital",      35.5606, 45.4185, "00:00-24:00", True),
    ("Zargatay Pharmacy",     "Zargatay District",       35.5470, 45.4290, "08:00-21:00", False),
    ("Ashti Pharmacy",        "Ashti District",          35.5810, 45.4205, "08:00-22:00", False),
    ("Chwarbakh Pharmacy",    "Chwarbakh",               35.5568, 45.4475, "08:00-23:00", False),
    ("Sabunkaran Pharmacy",   "Sabunkaran",              35.5632, 45.4271, "08:00-22:00", False),
    ("Bakrajo Pharmacy",      "Bakrajo Road",            35.5574, 45.3790, "09:00-21:00", False),
    ("Qularaisi Pharmacy",    "Qularaisi",               35.5660, 45.4460, "08:00-22:00", False),
    ("Kurdsat Pharmacy",      "Kurdsat District",        35.5452, 45.4152, "08:00-23:00", False),
    ("Sarchnar Pharmacy",     "Sarchnar",                35.5728, 45.4049, "08:00-22:00", False),
    ("Shorsh Pharmacy",       "Shorsh District",         35.5503, 45.4361, "00:00-24:00", True),
]

# (brand, name_ar, name_ku, active_ingredient, strength, form, company, general_use, rx_required)
MEDICINES = [
    # --- Pain / fever ---
    ("Panadol",        "بنادول",      "پانادۆڵ",     "Paracetamol", "500 mg", "tablet", "Haleon",
     "Relief of mild to moderate pain and fever.", False),
    ("Adol",           "أدول",        "ئەدۆڵ",       "Paracetamol", "500 mg", "tablet", "Julphar",
     "Relief of mild to moderate pain and fever.", False),
    ("Paracetamol",    "باراسيتامول", "پاراسیتامۆڵ", "Paracetamol", "500 mg", "tablet", "Generic (demo)",
     "Relief of mild to moderate pain and fever.", False),
    ("Brufen",         "بروفين",      "برووفین",     "Ibuprofen", "400 mg", "tablet", "Abbott",
     "Relief of pain, inflammation and fever (NSAID).", False),
    ("Nurofen",        "نوروفين",     "نووڕۆفین",    "Ibuprofen", "400 mg", "tablet", "Reckitt",
     "Relief of pain, inflammation and fever (NSAID).", False),
    ("Ibuprofen",      "ايبوبروفين",  "ئیبوپرۆفین",  "Ibuprofen", "400 mg", "tablet", "Generic (demo)",
     "Relief of pain, inflammation and fever (NSAID).", False),
    ("Voltaren",       "فولتارين",    "ڤۆڵتارین",    "Diclofenac sodium", "50 mg", "tablet", "Novartis",
     "Relief of pain and inflammation (NSAID).", True),
    ("Diclofenac",     "ديكلوفيناك",  "دیکلۆفیناک",  "Diclofenac sodium", "50 mg", "tablet", "Generic (demo)",
     "Relief of pain and inflammation (NSAID).", True),
    ("Aspirin Protect","أسبرين",      "ئەسپرین",     "Acetylsalicylic acid", "100 mg", "tablet", "Bayer",
     "Low-dose aspirin, used to help prevent blood clots as directed by a doctor.", False),

    # --- Antibiotics (prescription) ---
    ("Amoxil",         "أموكسيل",     "ئەمۆکسیل",    "Amoxicillin", "500 mg", "capsule", "GSK",
     "Antibiotic for bacterial infections.", True),
    ("Amoxicillin",    "أموكسيسيلين", "ئەمۆکسیسیلین","Amoxicillin", "500 mg", "capsule", "Generic (demo)",
     "Antibiotic for bacterial infections.", True),
    ("Augmentin",      "أوجمنتين",    "ئۆگمێنتین",   "Amoxicillin + Clavulanic acid", "625 mg", "tablet", "GSK",
     "Antibiotic for bacterial infections.", True),
    ("Amoxiclav",      "أموكسيكلاف",  "ئەمۆکسیکلاڤ", "Amoxicillin + Clavulanic acid", "625 mg", "tablet", "Generic (demo)",
     "Antibiotic for bacterial infections.", True),
    ("Zithromax",      "زيثروماكس",   "زیترۆماکس",   "Azithromycin", "500 mg", "tablet", "Pfizer",
     "Antibiotic for bacterial infections.", True),
    ("Azithromycin",   "أزيثرومايسين","ئەزیترۆمایسین","Azithromycin", "500 mg", "tablet", "Generic (demo)",
     "Antibiotic for bacterial infections.", True),
    ("Ciprobay",       "سيبروباي",    "سیپرۆبای",    "Ciprofloxacin", "500 mg", "tablet", "Bayer",
     "Antibiotic for bacterial infections.", True),
    ("Ciprofloxacin",  "سيبروفلوكساسين","سیپرۆفلۆکساسین","Ciprofloxacin", "500 mg", "tablet", "Generic (demo)",
     "Antibiotic for bacterial infections.", True),
    ("Flagyl",         "فلاجيل",      "فلاجیل",      "Metronidazole", "500 mg", "tablet", "Sanofi",
     "Treatment of certain bacterial and parasitic infections.", True),

    # --- Stomach ---
    ("Losec",          "لوسك",        "لۆسێک",       "Omeprazole", "20 mg", "capsule", "AstraZeneca",
     "Reduces stomach acid (heartburn, reflux, ulcers).", False),
    ("Omeprazole",     "أوميبرازول",  "ئۆمیپرازۆڵ",  "Omeprazole", "20 mg", "capsule", "Generic (demo)",
     "Reduces stomach acid (heartburn, reflux, ulcers).", False),
    ("Nexium",         "نيكسيوم",     "نێکسیۆم",     "Esomeprazole", "40 mg", "tablet", "AstraZeneca",
     "Reduces stomach acid (heartburn, reflux, ulcers).", True),
    ("Motilium",       "موتيليوم",    "مۆتیلیۆم",    "Domperidone", "10 mg", "tablet", "Janssen",
     "Relief of nausea and vomiting.", True),
    ("Buscopan",       "بسكوبان",     "بوسکۆپان",    "Hyoscine butylbromide", "10 mg", "tablet", "Sanofi",
     "Relief of stomach and intestinal cramps.", False),
    ("Imodium",        "إيموديوم",    "ئیمۆدیۆم",    "Loperamide", "2 mg", "capsule", "Kenvue",
     "Short-term relief of diarrhoea.", False),

    # --- Allergy ---
    ("Zyrtec",         "زيرتك",       "زیرتێک",      "Cetirizine", "10 mg", "tablet", "UCB",
     "Relief of allergy symptoms (antihistamine).", False),
    ("Cetirizine",     "سيتريزين",    "سێتریزین",    "Cetirizine", "10 mg", "tablet", "Generic (demo)",
     "Relief of allergy symptoms (antihistamine).", False),
    ("Claritine",      "كلاريتين",    "کلاریتین",    "Loratadine", "10 mg", "tablet", "Bayer",
     "Relief of allergy symptoms (antihistamine).", False),
    ("Telfast",        "تلفاست",      "تێلفاست",     "Fexofenadine", "120 mg", "tablet", "Sanofi",
     "Relief of allergy symptoms (antihistamine).", False),

    # --- Chronic conditions (prescription) ---
    ("Glucophage",     "جلوكوفاج",    "گلوکۆفاج",    "Metformin", "500 mg", "tablet", "Merck",
     "Treatment of type 2 diabetes.", True),
    ("Metformin",      "ميتفورمين",   "میتفۆرمین",   "Metformin", "500 mg", "tablet", "Generic (demo)",
     "Treatment of type 2 diabetes.", True),
    ("Norvasc",        "نورفاسك",     "نۆرڤاسک",     "Amlodipine", "5 mg", "tablet", "Pfizer",
     "Treatment of high blood pressure and angina.", True),
    ("Amlodipine",     "أملوديبين",   "ئەملۆدیپین",  "Amlodipine", "5 mg", "tablet", "Generic (demo)",
     "Treatment of high blood pressure and angina.", True),
    ("Cozaar",         "كوزار",       "کۆزار",       "Losartan", "50 mg", "tablet", "Organon",
     "Treatment of high blood pressure.", True),
    ("Lipitor",        "ليبيتور",     "لیپیتۆر",     "Atorvastatin", "20 mg", "tablet", "Pfizer",
     "Lowers cholesterol.", True),
    ("Atorvastatin",   "أتورفاستاتين","ئەتۆرڤاستاتین","Atorvastatin", "20 mg", "tablet", "Generic (demo)",
     "Lowers cholesterol.", True),
    ("Ventolin",       "فنتولين",     "ڤێنتۆلین",    "Salbutamol", "100 mcg/dose", "inhaler", "GSK",
     "Relief of asthma and breathing difficulty (reliever inhaler).", True),

    # --- Same ingredient, different strength: good for testing the "strength differs" flag later ---
    ("Panadol Extra",  "بنادول اكسترا","پانادۆڵ ئێکسترا","Paracetamol + Caffeine", "500 mg + 65 mg", "tablet", "Haleon",
     "Relief of mild to moderate pain.", False),
    ("Brufen 600",     "بروفين 600",  "برووفین 600",  "Ibuprofen", "600 mg", "tablet", "Abbott",
     "Relief of pain, inflammation and fever (NSAID).", True),

    # --- Real boxes photographed in a Sulaymaniyah pharmacy (Nov 2026) ---
    ("Adol Drops",     "أدول نقط",    "ئەدۆڵ دڵۆپ",  "Paracetamol", "100 mg/mL", "oral drops", "Julphar",
     "Relief of pain and fever in infants and children.", False),
    ("Piodol Advance", "بيودول أدفانس","پیۆدۆڵ ئەدڤانس","Paracetamol", "500 mg", "tablet", "Pioneer (Iraq)",
     "Relief of mild to moderate pain and fever.", False),
    ("Avodol",         "أفودول",      "ئەڤۆدۆڵ",     "Paracetamol", "1000 mg", "tablet", "AVO",
     "Relief of mild to moderate pain and fever.", False),
    ("Ibuprofen Suspension", "ايبوبروفين شراب", "شەربەتی ئیبوپرۆفین", "Ibuprofen", "100 mg/5 mL", "oral suspension",
     "Hayat Drug Production (Baghdad)", "Relief of pain, fever and inflammation in children.", True),
    ("Olfen-50",       "أولفين 50",   "ئۆلفێن 50",   "Diclofenac sodium", "50 mg", "tablet", "Acino",
     "Relief of pain and inflammation (NSAID).", True),
    ("Voltastar-K",    "فولتاستار ك", "ڤۆڵتاستار-ک", "Diclofenac potassium", "50 mg", "sachet", "Ibn Al Haytham Pharma",
     "Relief of pain and inflammation (NSAID).", True),
    ("Amoxicillin Normon", "أموكسيسيلين نورمون", "ئەمۆکسیسیلین نۆرمۆن", "Amoxicillin", "500 mg", "capsule",
     "Laboratorios Normon (Spain)", "Antibiotic for bacterial infections.", True),
    ("Clavmark 1000",  "كلافمارك 1000","کلاڤمارک 1000","Amoxicillin + Clavulanic acid", "1000 mg", "tablet", "Marksans Pharma",
     "Antibiotic for bacterial infections.", True),
    ("Gasec",          "جاسك",        "گاسێک",       "Omeprazole", "20 mg", "capsule", "Acino",
     "Reduces stomach acid (heartburn, reflux, ulcers).", False),
    ("Ome TAD",        "أومي تاد",    "ئۆمێ تاد",    "Omeprazole", "20 mg", "capsule", "TAD Pharma (Germany)",
     "Reduces stomach acid (heartburn, reflux, ulcers).", False),
    ("Nexium 20",      "نيكسيوم 20",  "نێکسیۆم 20",  "Esomeprazole", "20 mg", "tablet", "AstraZeneca",
     "Reduces stomach acid (heartburn, reflux, ulcers).", True),
    ("Hyoscine-N-Butylbromide", "هيوسين بيوتيل بروميد", "هایۆسین بیوتیل برۆمید", "Hyoscine butylbromide", "20 mg/mL",
     "injection", "Alborz Darou", "Relief of stomach and intestinal spasms. Given by a health professional.", True),
    ("Allercet",       "أليرسيت",     "ئەلێرسێت",    "Cetirizine", "10 mg", "tablet", "Micro Labs",
     "Relief of allergy symptoms (antihistamine).", False),
    ("Fexet",          "فيكسيت",      "فێکسێت",      "Fexofenadine", "180 mg", "tablet", "Getz Pharma",
     "Relief of allergy symptoms (antihistamine).", True),
]

# Phase 7: "controlled" medicines (abuse risk). They can never be reserved online, only bought
# in person. A medicine is controlled if any of its active ingredients is in this list.
# None of the 52 demo medicines is controlled today; this is ready for when one is added.
# Have a pharmacist check this list.
CONTROLLED_INGREDIENTS = {
    "Tramadol", "Codeine", "Morphine", "Pregabalin", "Gabapentin",
    "Diazepam", "Alprazolam", "Clonazepam", "Lorazepam", "Zolpidem",
}


# Translations of each "general use" sentence: English -> (Arabic, Kurdish).
# Every general_use in MEDICINES above must appear here (seed.py checks this).
# Have a pharmacist or native speaker check these before the showcase.
USE_TRANSLATIONS = {
    "Relief of mild to moderate pain and fever.": (
        "تخفيف الألم الخفيف إلى المتوسط والحمى.",
        "کەمکردنەوەی ئازاری سووک تا مامناوەند و تا."),
    "Relief of mild to moderate pain.": (
        "تخفيف الألم الخفيف إلى المتوسط.",
        "کەمکردنەوەی ئازاری سووک تا مامناوەند."),
    "Relief of pain, inflammation and fever (NSAID).": (
        "تخفيف الألم والالتهاب والحمى (مضاد التهاب غير ستيرويدي).",
        "کەمکردنەوەی ئازار و هەوکردن و تا (دژەهەوکردنی ناستیرۆیدی)."),
    "Relief of pain and inflammation (NSAID).": (
        "تخفيف الألم والالتهاب (مضاد التهاب غير ستيرويدي).",
        "کەمکردنەوەی ئازار و هەوکردن (دژەهەوکردنی ناستیرۆیدی)."),
    "Low-dose aspirin, used to help prevent blood clots as directed by a doctor.": (
        "أسبرين بجرعة منخفضة، يُستخدم للمساعدة في منع الجلطات الدموية حسب توجيه الطبيب.",
        "ئەسپرینی ژەمی کەم، بۆ یارمەتیدان لە ڕێگرتن لە مەیینی خوێن بەپێی ڕێنمایی پزیشک."),
    "Antibiotic for bacterial infections.": (
        "مضاد حيوي لعلاج الالتهابات البكتيرية.",
        "دژەزیندە بۆ هەوکردنی بەکتریایی."),
    "Treatment of certain bacterial and parasitic infections.": (
        "علاج بعض الالتهابات البكتيرية والطفيلية.",
        "چارەسەری هەندێک هەوکردنی بەکتریایی و مشەخۆری."),
    "Reduces stomach acid (heartburn, reflux, ulcers).": (
        "يقلل حموضة المعدة (الحرقة، الارتجاع، القرحة).",
        "ترشی گەدە کەم دەکاتەوە (سووتانەوەی سنگ، گەڕانەوەی ترشی، برینی گەدە)."),
    "Relief of nausea and vomiting.": (
        "تخفيف الغثيان والقيء.",
        "کەمکردنەوەی دڵتێکەڵهاتن و ڕشانەوە."),
    "Relief of stomach and intestinal cramps.": (
        "تخفيف تقلصات المعدة والأمعاء.",
        "کەمکردنەوەی گرژبوونی گەدە و ڕیخۆڵە."),
    "Short-term relief of diarrhoea.": (
        "تخفيف الإسهال لفترة قصيرة.",
        "کەمکردنەوەی سکچوون بۆ ماوەیەکی کورت."),
    "Relief of allergy symptoms (antihistamine).": (
        "تخفيف أعراض الحساسية (مضاد للهيستامين).",
        "کەمکردنەوەی نیشانەکانی هەستیاری (دژەهیستامین)."),
    "Treatment of type 2 diabetes.": (
        "علاج داء السكري من النوع الثاني.",
        "چارەسەری نەخۆشی شەکرەی جۆری دووەم."),
    "Treatment of high blood pressure and angina.": (
        "علاج ارتفاع ضغط الدم والذبحة الصدرية.",
        "چارەسەری بەرزی پەستانی خوێن و ئازاری سنگ (ئەنجاینا)."),
    "Treatment of high blood pressure.": (
        "علاج ارتفاع ضغط الدم.",
        "چارەسەری بەرزی پەستانی خوێن."),
    "Lowers cholesterol.": (
        "يخفض الكوليسترول.",
        "کۆلیسترۆڵ کەم دەکاتەوە."),
    "Relief of pain and fever in infants and children.": (
        "تخفيف الألم والحمى عند الرضع والأطفال.",
        "کەمکردنەوەی ئازار و تا لە ساوا و منداڵاندا."),
    "Relief of pain, fever and inflammation in children.": (
        "تخفيف الألم والحمى والالتهاب عند الأطفال.",
        "کەمکردنەوەی ئازار و تا و هەوکردن لە منداڵاندا."),
    "Relief of stomach and intestinal spasms. Given by a health professional.": (
        "تخفيف تشنجات المعدة والأمعاء. يُعطى من قبل كادر صحي.",
        "کەمکردنەوەی گرژبوونی گەدە و ڕیخۆڵە. لەلایەن کارمەندی تەندروستییەوە دەدرێت."),
    "Relief of asthma and breathing difficulty (reliever inhaler).": (
        "تخفيف الربو وصعوبة التنفس (بخاخ إسعافي).",
        "کەمکردنەوەی ڕەبۆ و هەناسەتەنگی (هەڵمژەری خێرا)."),
}


# Demo scenario: these brands are carried by pharmacies but sold out everywhere,
# so scanning/searching them shows "not available, but here are alternatives nearby".
DEMO_OUT_OF_STOCK = ["Gasec"]

# ...and these are never out of stock, so the alternative is always there.
# Gasec and Ome TAD are both omeprazole 20 mg capsules: you have both boxes.
DEMO_ALWAYS_IN_STOCK = ["Ome TAD"]


# Barcodes read from the photographed boxes (photo/<folder>), or typed from the box.
# brand_name -> list of (code, kind). The first one is the main product barcode.
BARCODES = {
    "Adol Drops":           [("6291100081394", "EAN-13")],
    "Piodol Advance":       [("6251875001287", "EAN-13")],
    "Avodol":               [("8904187888753", "EAN-13")],
    "Ibuprofen Suspension": [("501862012802020", "Code 128")],
    "Brufen":               [("8002660035349", "EAN-13")],
    "Olfen-50":             [("7640153080653", "EAN-13")],
    "Voltastar-K":          [("6211736204455", "EAN-13")],
    "Amoxicillin Normon":   [("8435232317558", "EAN-13")],
    "Clavmark 1000":        [("8906044906501", "EAN-13")],
    "Gasec":                [("7640153082848", "EAN-13")],
    "Ome TAD":              [("4260108281961", "EAN-13")],
    "Nexium 20":            [("5000456060479", "EAN-13"), ("9010410060519", "EAN-13")],
    "Allercet":             [("8901302097748", "EAN-13")],
    "Fexet":                [("8964003535193", "EAN-13")],
    "Claritine":            [("6285074003414", "EAN-13")],
    # Hyoscine-N-Butylbromide: no barcode on the box
}

# Official prices printed on the KMCA sticker of the boxes we photographed (IQD).
# Every pharmacy uses this price instead of a random one.
STICKER_PRICES = {
    "Adol Drops": 3000,
    "Clavmark 1000": 5000,
}

# Which photo folder (photo/<folder>) shows which medicine.
PHOTO_FOLDERS = {
    "adol": "Adol Drops",
    "Allercet": "Allercet",
    "Amoxicillin": "Amoxicillin Normon",
    "avodol": "Avodol",
    "Brufen": "Brufen",
    "Claritine": "Claritine",
    "fexet": "Fexet",
    "gasec": "Gasec",
    "Hyoscine-N-Butylbromide": "Hyoscine-N-Butylbromide",
    "IBUPROFEN": "Ibuprofen Suspension",
    "Klavmark": "Clavmark 1000",
    "Nexium": "Nexium 20",
    "olfen": "Olfen-50",
    "Ome TAD": "Ome TAD",
    "Piodol": "Piodol Advance",
    "voltastar-k": "Voltastar-K",
}


# ---------------- Phase 5: pharmacist dashboard ----------------
# Every pharmacy gets a login: username = first word of its name in lower case
# (Shifa Pharmacy -> "shifa"), password = DEMO_PASSWORD. Demo only!
DEMO_PASSWORD = "pharma123"

# Phase 9: demo delivery drivers (invented). Log in at /driver with these usernames and DRIVER_PASSWORD.
# (name, phone, username)
DEMO_DRIVERS = [
    ("Aram Omar",    "0750 410 2201", "aram"),
    ("Dana Rasul",   "0770 552 3802", "dana"),
    ("Hemn Kareem",  "0751 663 9403", "hemn"),
]
DRIVER_PASSWORD = "driver123"

# Fake search history for the last 14 days, so the dashboard has something to show.
DEMO_SEARCH_DAYS = 14
DEMO_SEARCH_COUNT = 700
# How popular each medicine is in the fake searches (others get weight 1).
DEMO_SEARCH_WEIGHTS = {
    "Panadol": 14, "Gasec": 12, "Augmentin": 10, "Brufen": 9, "Allercet": 8, "Zyrtec": 7,
    "Losec": 6, "Nexium 20": 6, "Amoxil": 6, "Voltaren": 5, "Fexet": 5, "Adol Drops": 5,
    "Piodol Advance": 5, "Glucophage": 5, "Ventolin": 4, "Ome TAD": 4, "Clavmark 1000": 4,
    "Ibuprofen Suspension": 4, "Claritine": 3, "Buscopan": 3,
}
# Searches for medicines that are NOT in PharmaFind at all (found = False).
DEMO_NOT_FOUND = {"Concor 5": 9, "Euthyrox 50": 7, "Lantus": 6, "Xarelto 20": 4, "Crestor 10": 4, "Ozempic": 3}
