"""Seed skill taxonomy used by the deterministic ATS parser.

Aliases are deliberately conservative: a match is useful only when an HR
reviewer can trace it to a literal line in the CV.  The database integration in
Phase 2 may replace or extend these seeds.
"""

SKILLS = [
    {"id": "amadeus", "canonical": "Amadeus", "category": "gds_ticketing", "aliases": ["amadeus", "اماديوس", "أماديوس"]},
    {"id": "sabre", "canonical": "Sabre", "category": "gds_ticketing", "aliases": ["sabre", "saber gds", "سيبر", "سابري"]},
    {"id": "galileo", "canonical": "Galileo / Travelport", "category": "gds_ticketing", "aliases": ["galileo", "travelport", "جاليليو", "ترافل بورت"]},
    {"id": "iata", "canonical": "IATA", "category": "gds_ticketing", "aliases": ["iata", "اياتا", "اتحاد النقل الجوي الدولي"]},
    {"id": "bsp", "canonical": "BSP", "category": "gds_ticketing", "aliases": ["bsp", "billing and settlement plan", "نظام التسوية البنكية"]},
    {"id": "fare_rules", "canonical": "Fare rules", "category": "gds_ticketing", "aliases": ["fare rules", "fare construction", "قواعد الاسعار", "قواعد الأسعار"]},
    {"id": "pnr", "canonical": "PNR", "category": "gds_ticketing", "aliases": ["pnr", "passenger name record", "سجل الحجز", "ملف الحجز"]},
    {"id": "refunds_reissue", "canonical": "Refunds and reissue", "category": "gds_ticketing", "aliases": ["refunds and reissue", "refund and reissue", "reissue", "refunds", "استرجاع واعادة اصدار", "استرداد واعادة اصدار", "إعادة إصدار"]},
    {"id": "lcc_portals", "canonical": "LCC portals", "category": "gds_ticketing", "aliases": ["lcc portals", "low cost carrier portals", "budget airline portals", "بوابات الطيران الاقتصادي"]},
    {"id": "ndc", "canonical": "NDC", "category": "gds_ticketing", "aliases": ["ndc", "new distribution capability", "قدرات التوزيع الجديدة"]},
    {"id": "gds", "canonical": "GDS systems", "category": "gds_ticketing", "aliases": ["gds", "global distribution system", "amadeus", "sabre", "galileo", "travelport", "نظام التوزيع العالمي", "اماديوس", "سيبر", "جاليليو"]},
    {"id": "airline_distribution", "canonical": "Airline distribution systems", "category": "gds_ticketing", "aliases": ["airline distribution", "global distribution system", "gds", "ndc", "new distribution capability", "amadeus", "sabre", "galileo", "travelport", "توزيع شركات الطيران", "نظام التوزيع العالمي", "قدرات التوزيع الجديدة", "اماديوس", "سيبر", "جاليليو"]},
    {"id": "airline_portals", "canonical": "Airline and LCC portals", "category": "gds_ticketing", "aliases": ["airline portals", "lcc portals", "ndc portals", "flynas", "flyadeal", "flydubai", "saudia", "nas air", "بوابات شركات الطيران", "بوابات الطيران الاقتصادي", "طيران ناس", "طيران اديل", "فلاي دبي", "الخطوط السعودية"]},
    {"id": "ticketing_operations", "canonical": "Reservation and ticketing operations", "category": "gds_ticketing", "aliases": ["reservation agent", "reservation officer", "ticketing agent", "ticketing officer", "reservations and ticketing", "air ticketing", "موظف حجز", "موظف حجوزات", "موظف تذاكر", "حجز واصدار تذاكر", "الحجز والتذاكر", "تذاكر"]},

    {"id": "flight_booking", "canonical": "Flight booking", "category": "travel_product", "aliases": ["flight booking", "flight bookings", "flight reservation", "flight reservations", "air booking", "airline reservation", "air ticketing", "booking flights", "حجز الطيران", "حجوزات الطيران", "حجز الرحلات", "حجز التذاكر", "تذاكر الطيران"]},
    {"id": "hotel_booking", "canonical": "Hotel booking", "category": "travel_product", "aliases": ["hotel booking", "hotel bookings", "hotel reservation", "hotel reservations", "accommodation booking", "booking hotels", "حجز الفنادق", "حجوزات الفنادق", "حجز فندقي"]},
    {"id": "umrah_hajj", "canonical": "Umrah and Hajj packages", "category": "travel_product", "aliases": ["umrah", "hajj", "umrah packages", "hajj packages", "umrah and hajj", "umrah booking", "hajj booking", "برامج العمرة", "باقات العمرة", "برامج الحج", "الحج والعمرة", "العمرة", "عمرة", "الحج"]},
    {"id": "visa_processing", "canonical": "Visa processing", "category": "travel_product", "aliases": ["visa", "visas", "visa processing", "visa services", "visa applications", "تأشيرة", "تاشيرة", "تأشيرات", "التاشيرات", "معالجة التاشيرات", "خدمات التاشيرات"]},
    {"id": "visa_consulting", "canonical": "Visa consulting", "category": "travel_product", "aliases": ["visa consultant", "visa officer", "visa specialist", "immigration consultant", "مستشار تاشيرات", "موظف تاشيرات", "اخصائي تاشيرات"]},
    {"id": "travel_consulting", "canonical": "Travel consulting", "category": "travel_product", "aliases": ["travel consultant", "travel counselor", "travel agent", "tour consultant", "استشاري سفر", "مستشار سفر", "موظف سياحة", "وكيل سفر"]},
    {"id": "corporate_travel", "canonical": "Corporate travel", "category": "travel_product", "aliases": ["corporate travel", "business travel", "corporate accounts", "business trips", "سفر الشركات", "رحلات الاعمال", "حسابات الشركات"]},
    {"id": "tours", "canonical": "Tours", "category": "travel_product", "aliases": ["tours", "tour packages", "sightseeing", "برامج سياحية", "الجولات السياحية", "رحلات سياحية"]},
    {"id": "car_rental", "canonical": "Car rental", "category": "travel_product", "aliases": ["car rental", "car hire", "تاجير السيارات", "تأجير السيارات"]},
    {"id": "hotelbeds", "canonical": "Hotelbeds", "category": "travel_product", "aliases": ["hotelbeds", "hotel beds", "هوتيل بدز"]},
    {"id": "webbeds", "canonical": "WebBeds", "category": "travel_product", "aliases": ["webbeds", "web beds", "ويب بدز"]},
    {"id": "tbo", "canonical": "TBO", "category": "travel_product", "aliases": ["tbo", "tbo holidays", "تي بي او"]},

    {"id": "bitrix24", "canonical": "Bitrix24", "category": "sales_crm", "aliases": ["bitrix24", "bitrix 24", "بيتريكس24", "بيتريكس 24"]},
    {"id": "cold_calling", "canonical": "Cold calling", "category": "sales_crm", "aliases": ["cold calling", "outbound calls", "الاتصال البارد", "مكالمات المبيعات"]},
    {"id": "upselling", "canonical": "Upselling", "category": "sales_crm", "aliases": ["upselling", "up-selling", "cross selling", "زيادة المبيعات", "البيع الاضافي"]},
    {"id": "quotations", "canonical": "Quotations", "category": "sales_crm", "aliases": ["quotations", "sales quotes", "عروض الاسعار", "عرض سعر"]},
    {"id": "whatsapp_sales", "canonical": "WhatsApp sales", "category": "sales_crm", "aliases": ["whatsapp sales", "selling via whatsapp", "مبيعات واتساب", "البيع عبر الواتساب"]},
    {"id": "digital_marketing", "canonical": "Digital marketing", "category": "sales_crm", "aliases": ["digital marketing", "online marketing", "التسويق الرقمي", "التسويق الالكتروني"]},
    {"id": "social_media", "canonical": "Social media management", "category": "sales_crm", "aliases": ["social media management", "social media", "ادارة وسائل التواصل", "إدارة مواقع التواصل"]},
    {"id": "seo", "canonical": "SEO", "category": "sales_crm", "aliases": ["seo", "search engine optimization", "تحسين محركات البحث"]},
    {"id": "media_buying", "canonical": "Media buying", "category": "sales_crm", "aliases": ["media buying", "media buyer", "paid media", "paid campaigns", "شراء وسائل الاعلام", "شراء المساحات الاعلانية", "الحملات المدفوعة"]},

    {"id": "excel", "canonical": "Microsoft Excel", "category": "office", "aliases": ["microsoft excel", "ms excel", "excel", "اكسل", "إكسل"]},
    {"id": "word", "canonical": "Microsoft Word", "category": "office", "aliases": ["microsoft word", "ms word", "word", "وورد"]},
    {"id": "email_etiquette", "canonical": "Email etiquette", "category": "office", "aliases": ["email etiquette", "business email", "professional email", "مراسلات البريد الالكتروني", "البريد المهني"]},
    {"id": "arabic_typing", "canonical": "Arabic typing", "category": "office", "aliases": ["arabic typing", "typing in arabic", "الطباعة بالعربية", "الكتابة بالعربية"]},
    {"id": "english", "canonical": "English", "category": "office", "aliases": ["english", "اللغة الانجليزية", "الانجليزية"]},
    {"id": "data_analysis", "canonical": "Data analysis", "category": "office", "aliases": ["data analysis", "data analytics", "تحليل البيانات"]},
    {"id": "power_bi", "canonical": "Power BI", "category": "office", "aliases": ["power bi", "powerbi", "باور بي اي"]},
    {"id": "sql", "canonical": "SQL", "category": "office", "aliases": ["sql", "structured query language", "اس كيو ال"]},
    {"id": "microsoft_office", "canonical": "Microsoft Office", "category": "office", "aliases": ["microsoft office", "ms office", "office suite", "مايكروسوفت اوفيس", "حزمة اوفيس"]},
    {"id": "sap", "canonical": "SAP", "category": "office", "aliases": ["sap", "sap erp", "ساب"]},
    {"id": "oracle", "canonical": "Oracle", "category": "office", "aliases": ["oracle", "oracle erp", "اوراكل"]},
    {"id": "python", "canonical": "Python", "category": "office", "aliases": ["python", "python programming", "بايثون"]},

    {"id": "bookkeeping", "canonical": "Bookkeeping", "category": "finance", "aliases": ["bookkeeping", "record keeping", "مسك الدفاتر"]},
    {"id": "invoicing", "canonical": "Invoicing", "category": "finance", "aliases": ["invoicing", "billing", "invoice preparation", "الفوترة", "اعداد الفواتير"]},
    {"id": "vat_zatca", "canonical": "VAT / ZATCA", "category": "finance", "aliases": ["zatca", "vat", "value added tax", "هيئة الزكاة والضريبة والجمارك", "ضريبة القيمة المضافة"]},
    {"id": "zoho_books", "canonical": "Zoho Books", "category": "finance", "aliases": ["zoho books", "زوهو بوكس"]},
    {"id": "quickbooks", "canonical": "QuickBooks", "category": "finance", "aliases": ["quickbooks", "quick books", "كويك بوكس"]},

    {"id": "negotiation", "canonical": "Negotiation", "category": "soft", "aliases": ["negotiation", "negotiating", "التفاوض", "مهارات التفاوض"]},
    {"id": "customer_service", "canonical": "Customer service", "category": "soft", "aliases": ["customer service", "customer care", "client service", "خدمة العملاء", "العناية بالعملاء"]},
    {"id": "teamwork", "canonical": "Teamwork", "category": "soft", "aliases": ["teamwork", "team player", "working in a team", "العمل الجماعي", "العمل ضمن فريق"]},
    {"id": "leadership", "canonical": "Leadership", "category": "soft", "aliases": ["leadership", "team leadership", "قيادة الفريق", "القيادة"]},
    {"id": "branch_management", "canonical": "Branch management", "category": "management", "aliases": ["branch management", "branch manager", "managing branches", "ادارة الفروع", "ادارة فرع", "مدير فرع"]},
    {"id": "operations_management", "canonical": "Operations management", "category": "management", "aliases": ["operations management", "operations manager", "operational management", "ادارة العمليات", "مدير عمليات", "الادارة التشغيلية"]},
    {"id": "hr_operations", "canonical": "HR operations", "category": "hr", "aliases": ["hr operations", "human resources", "personnel administration", "عمليات الموارد البشرية", "الموارد البشرية", "شؤون الموظفين"]},
    {"id": "recruitment", "canonical": "Recruitment", "category": "hr", "aliases": ["recruitment", "talent acquisition", "hiring", "التوظيف", "استقطاب المواهب"]},
]

SKILLS_BY_ID = {skill["id"]: skill for skill in SKILLS}
