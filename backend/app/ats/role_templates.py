"""Editable starter roles for Phase 0.

These are plain dictionaries so they can be serialized directly when Phase 2
adds persistence.  Skill references always use taxonomy ids.
"""

DEFAULT_WEIGHTS = {
    "required_skills": 40,
    "experience": 20,
    "preferred_skills": 10,
    "education": 10,
    "languages": 10,
}

HARD_GATES_AVAILABLE = [
    "nationality_in",
    "city_in",
    "language_required",
    "min_years",
    "min_education",
    "licence_required",
    "transferable_iqama_required",
]


def _role(role_id, title, required, preferred, years, education, languages, keywords):
    return {
        "id": role_id,
        "title": title,
        "required_skills": required,
        "preferred_skills": preferred,
        "min_years": years,
        "min_education": education,
        "languages": languages,
        "gates": {},
        "hard_gates_available": list(HARD_GATES_AVAILABLE),
        "weights": dict(DEFAULT_WEIGHTS),
        "similarity_text": " ".join([
            title,
            *(skill.replace("_", " ") for skill in required),
            *(skill.replace("_", " ") for skill in preferred),
            *keywords,
        ]),
    }


ROLE_TEMPLATES = [
    _role("reservation_ticketing", "Reservation & Ticketing Officer",
          ["ticketing_operations", "airline_distribution", "refunds_reissue"],
          ["amadeus", "galileo", "ndc"],
          2, "diploma", ["English", "Arabic"],
          ["airline reservations", "ticketing", "GDS", "حجوزات الطيران", "اصدار التذاكر"]),
    _role("travel_consultant", "Travel Consultant",
          ["travel_consulting", "hotel_booking", "tours"],
          ["gds", "customer_service", "corporate_travel", "tbo"],
          2, "diploma", ["English", "Arabic"],
          ["travel consultant", "holiday packages", "itinerary", "استشاري سفر", "برامج سياحية"]),
    _role("visa_consultant", "Visa Consultant",
          ["visa_consulting", "visa_processing"],
          ["customer_service", "email_etiquette", "quotations"],
          2, "bachelor", ["English", "Arabic"],
          ["visa consultant", "embassy", "documentation", "immigration", "تاشيرات", "سفارات"]),
    _role("branch_operations_manager", "Branch/Operations Manager",
          ["branch_management", "operations_management"],
          ["leadership", "negotiation"],
          5, "bachelor", ["English", "Arabic"],
          ["branch manager", "operations manager", "team management", "مدير فرع", "مدير عمليات"]),
    _role("marketing_specialist", "Marketing Specialist",
          ["digital_marketing", "media_buying", "social_media"],
          ["seo"],
          2, "bachelor", ["English", "Arabic"],
          ["marketing specialist", "campaigns", "content", "مسوق", "اخصائي تسويق"]),
    _role("hr_customer_service", "HR & Customer Service",
          ["hr_operations", "recruitment", "customer_service"],
          ["excel", "word", "microsoft_office", "email_etiquette", "teamwork"],
          2, "bachelor", ["English", "Arabic"],
          ["human resources", "customer support", "personnel", "موارد بشرية", "خدمة العملاء"]),
]

ROLE_TEMPLATES_BY_ID = {role["id"]: role for role in ROLE_TEMPLATES}
