"""Everything the assistant says, in English, French and Arabic.

Only wording lives here. Which questions are allowed is still decided in
security/rbac.py from the login session; a language can never change that.
English text stays exactly as rbac.py and pipeline.py define it.
"""
import re

LANGUAGES = {"en": "English", "fr": "Français", "ar": "العربية"}

INTENT_TEXT = {
    "count_new_accounts": ("Nombre de comptes ouverts sur une période", "عدد الحسابات المفتوحة خلال فترة"),
    "total_deposits": ("Montant et nombre de dépôts sur une période", "قيمة وعدد الإيداعات خلال فترة"),
    "total_withdrawals": ("Montant et nombre de retraits sur une période", "قيمة وعدد السحوبات خلال فترة"),
    "transaction_count": ("Nombre et montant des transactions sur une période", "عدد وقيمة المعاملات خلال فترة"),
    "count_active_loans": ("Nombre de prêts actifs et de clients concernés", "عدد القروض النشطة والعملاء أصحابها"),
    "count_customers": ("Nombre total de clients", "إجمالي عدد العملاء"),
    "avg_loan_amount": ("Montant moyen des prêts", "متوسط مبلغ القروض"),
    "total_loan_portfolio": ("Valeur totale des prêts actifs", "القيمة الإجمالية للقروض النشطة"),
    "total_balance_by_type": ("Solde total par type de compte", "إجمالي الرصيد حسب نوع الحساب"),
    "avg_account_balance": ("Solde moyen par type de compte", "متوسط الرصيد حسب نوع الحساب"),
    "new_accounts_trend": ("Comptes ouverts par mois sur les N derniers mois", "الحسابات المفتوحة شهريا خلال آخر N أشهر"),
    "largest_transactions": ("Les plus grandes transactions d'une période", "أكبر المعاملات خلال فترة"),
    "spending_by_category": ("Retraits par catégorie de dépense sur une période", "السحوبات حسب فئة الإنفاق خلال فترة"),
    "loan_repayment_schedule": ("Remboursements de prêts attendus par mois", "أقساط القروض المتوقعة كل شهر"),
    "balance_trend": ("Solde total à la fin de chacun des N derniers mois", "الرصيد الإجمالي في نهاية كل شهر من آخر N أشهر"),
    "my_balance": ("Les soldes de vos propres comptes", "أرصدة حساباتك الخاصة"),
    "my_recent_transactions": ("Vos dernières transactions", "آخر معاملاتك"),
}

COLUMNS = {
    "new_accounts": ("nouveaux comptes", "حسابات جديدة"),
    "deposit_count": ("nombre de dépôts", "عدد الإيداعات"),
    "total_deposits": ("total des dépôts", "إجمالي الإيداعات"),
    "withdrawal_count": ("nombre de retraits", "عدد السحوبات"),
    "total_withdrawals": ("total des retraits", "إجمالي السحوبات"),
    "transaction_count": ("nombre de transactions", "عدد المعاملات"),
    "total_amount": ("montant total", "المبلغ الإجمالي"),
    "active_loans": ("prêts actifs", "القروض النشطة"),
    "customers_with_active_loans": ("clients avec un prêt actif", "العملاء الذين لديهم قرض نشط"),
    "customers": ("clients", "العملاء"),
    "avg_loan_amount": ("montant moyen du prêt", "متوسط مبلغ القرض"),
    "loan_count": ("nombre de prêts", "عدد القروض"),
    "total_active_loan_amount": ("montant total des prêts actifs", "إجمالي مبلغ القروض النشطة"),
    "account_type": ("type de compte", "نوع الحساب"),
    "accounts": ("comptes", "الحسابات"),
    "total_balance": ("solde total", "إجمالي الرصيد"),
    "avg_balance": ("solde moyen", "متوسط الرصيد"),
    "month": ("mois", "الشهر"),
    "transaction_id": ("n° de transaction", "رقم المعاملة"),
    "account": ("compte", "الحساب"),
    "transaction_type": ("type", "النوع"),
    "amount": ("montant", "المبلغ"),
    "transaction_date": ("date", "التاريخ"),
    "balance": ("solde", "الرصيد"),
    "category": ("catégorie", "الفئة"),
    "total_spent": ("total dépensé", "إجمالي الإنفاق"),
    "installments": ("échéances", "الأقساط"),
    "expected_repayments": ("remboursements attendus", "المدفوعات المتوقعة"),
    "end_of_month_balance": ("solde de fin de mois", "الرصيد في نهاية الشهر"),
}
VALUES = {
    "savings": ("épargne", "توفير"), "checking": ("courant", "جاري"),
    "deposit": ("dépôt", "إيداع"), "withdrawal": ("retrait", "سحب"),
    "groceries": ("alimentation", "البقالة"), "rent": ("loyer", "الإيجار"), "utilities": ("factures", "الفواتير"),
    "transport": ("transport", "النقل"), "dining": ("restaurants", "المطاعم"), "health": ("santé", "الصحة"),
    "shopping": ("achats", "التسوق"), "cash": ("espèces", "نقدا"),
}
_MONTHS = {
    "January": ("janvier", "يناير"), "February": ("février", "فبراير"), "March": ("mars", "مارس"),
    "April": ("avril", "أبريل"), "May": ("mai", "مايو"), "June": ("juin", "يونيو"),
    "July": ("juillet", "يوليو"), "August": ("août", "أغسطس"), "September": ("septembre", "سبتمبر"),
    "October": ("octobre", "أكتوبر"), "November": ("novembre", "نوفمبر"), "December": ("décembre", "ديسمبر"),
}
_PERIOD_WORDS = [  # order matters: longer phrases first
    ("all time", "toute la période", "كل الفترة"),
    ("yesterday", "hier", "أمس"),
    ("today", "aujourd'hui", "اليوم"),
    ("this week", "cette semaine", "هذا الأسبوع"),
    ("last week", "la semaine dernière", "الأسبوع الماضي"),
    ("this month", "ce mois-ci", "هذا الشهر"),
    (" so far", " à ce jour", " حتى الآن"),
    (", up to ", ", jusqu'au ", "، حتى "),
    (" to ", " au ", " إلى "),
]

_MESSAGES = {
    "according": ("Selon la base de données de la banque{period}, {values}.",
                  "حسب قاعدة بيانات البنك{period}: {values}."),
    "according_list": ("Selon la base de données de la banque{period} :", "حسب قاعدة بيانات البنك{period}:"),
    "no_records": ("La base de données de la banque ne contient aucun résultat{period}.",
                   "لا توجد سجلات مطابقة في قاعدة بيانات البنك{period}."),
    "period": (" pour {label}", " عن {label}"),
    "restricted_data": ("Accès refusé. Vous n'avez pas l'autorisation de consulter les dossiers, "
                        "coordonnées ou soldes individuels des clients.",
                        "تم رفض الوصول. ليس لديك إذن للاطلاع على سجلات العملاء أو بيانات الاتصال أو الأرصدة الفردية."),
    "out_of_scope": ("Désolé, je ne peux pas vous aider. Je réponds uniquement aux questions bancaires "
                     "approuvées, en lecture seule. Tapez « aide » pour voir ce que vous pouvez demander.",
                     "عذرا، لا يمكنني المساعدة في ذلك. أجيب فقط على الأسئلة المصرفية المعتمدة للقراءة فقط. "
                     "اكتب «مساعدة» لمعرفة ما يمكنك طرحه."),
    "role_not_permitted": ("Accès refusé. Votre rôle ({role}) ne permet pas de consulter : {what}.",
                           "تم رفض الوصول. دورك ({role}) لا يسمح بالاطلاع على: {what}."),
    "no_linked_customer": ("Accès refusé. Ce compte n'est lié à aucun client.",
                           "تم رفض الوصول. هذا الحساب غير مرتبط بأي عميل."),
    "not_authenticated": ("Veuillez d'abord vous connecter.", "يرجى تسجيل الدخول أولا."),
    "not_understood": ("Désolé, je n'ai pas compris cette question. Tapez « aide » pour voir les questions possibles.",
                       "عذرا، لم أفهم هذا السؤال. اكتب «مساعدة» لمعرفة الأسئلة الممكنة."),
    "invalid": ("Je n'ai pas pu exécuter cette demande : {detail}", "تعذر تنفيذ هذا الطلب: {detail}"),
    "database_error": ("Une erreur est survenue lors de la lecture de la base de données.",
                       "حدث خطأ أثناء قراءة قاعدة البيانات."),
    "blocked": ("J'ai trouvé l'information, mais cette réponse n'a pas passé les contrôles de confidentialité "
                "et d'exactitude. Veuillez reformuler votre question.",
                "وجدت المعلومات، لكن هذه الإجابة لم تجتز فحوصات الخصوصية والدقة. يرجى إعادة صياغة سؤالك."),
    "help_intro": ("En tant que {role}, vous pouvez demander :", "بصفتك {role}، يمكنك السؤال عن:"),
    "clarify": ("Je ne suis pas sûr d'avoir compris. Vouliez-vous dire :", "لست متأكدا من أنني فهمت. هل تقصد:"),
}
_ENGLISH_MESSAGES = {
    "clarify": "I'm not sure I understood. Did you mean:",
    "not_understood": "Sorry, I didn't understand that question. Type \"help\" to see the questions I can answer.",
}
ROLES = {"manager": ("responsable", "مدير"), "employee": ("employé", "موظف"), "customer": ("client", "عميل")}

UI = {
    "en": {"sign_in": "Sign in to continue", "new_chat": "New chat", "search": "Search chats", "recents": "Recents",
           "no_conversations": "No conversations yet.", "chatting_as": "Chatting as", "begin": "Where should we begin?",
           "disclaimer": "Answers come only from the bank database. Like any AI, it can make mistakes.", "settings": "Settings",
           "ask": "Ask a question about the bank (type \"help\" for ideas)", "try": "Try asking",
           "logout": "Log out", "role": "Role", "thinking": "Thinking...", "language": "Language",
           "tagline": "A secure banking assistant. Answers come only from approved, read-only queries.",
           "username": "Username", "password": "Password", "login": "Log in", "demo": "Demo accounts",
           "wrong_login": "Wrong username or password.", "locked": "Too many failed attempts. Please try again later.",
           "engine": "Engine", "engine_fast": "Fast (embedding parser + template answers, no model needed)",
           "engine_ai": "AI model (Qwen parser + AI-written answers)",
           "no_model": "The Qwen model is not downloaded yet, so only the fast engine is available.",
           "details_toggle": "Show query details (demo)", "own_only": "Customers can only see their own accounts.",
           "details": "Query details", "status": "Status", "parser": "Parser", "attempts": "attempts",
           "intent": "Intent", "params": "Parameters", "written_by": "Answer written by",
           "answer_language": "Language", "typos": "Typos fixed", "guard": "Output guard problems",
           "audit": "📋 Audit log (manager only, latest 20)", "no_entries": "No entries yet.",
           "dark": "🌙 Dark mode", "light": "☀️ Light mode",
           "manager": "Manager", "employee": "Employee", "customer": "Customer"},
    "fr": {"sign_in": "Connectez-vous pour continuer", "new_chat": "Nouvelle discussion", "search": "Rechercher", "recents": "Récents",
           "no_conversations": "Aucune discussion pour l'instant.", "chatting_as": "Connecté en tant que", "begin": "Par quoi commençons-nous ?",
           "disclaimer": "Les réponses proviennent uniquement de la base de données de la banque. Comme toute IA, elle peut se tromper.", "settings": "Paramètres",
           "ask": "Posez une question sur la banque (tapez « aide » pour des idées)", "try": "Essayez de demander",
           "logout": "Se déconnecter", "role": "Rôle", "thinking": "Réflexion...", "language": "Langue",
           "tagline": "Un assistant bancaire sécurisé. Les réponses proviennent uniquement de requêtes approuvées en lecture seule.",
           "username": "Nom d'utilisateur", "password": "Mot de passe", "login": "Se connecter",
           "demo": "Comptes de démonstration", "wrong_login": "Nom d'utilisateur ou mot de passe incorrect.",
           "locked": "Trop de tentatives échouées. Veuillez réessayer plus tard.",
           "engine": "Moteur", "engine_fast": "Rapide (analyse par similarité + réponses modèles, sans IA)",
           "engine_ai": "Modèle d'IA (analyse Qwen + réponses rédigées par l'IA)",
           "no_model": "Le modèle Qwen n'est pas encore téléchargé : seul le moteur rapide est disponible.",
           "details_toggle": "Afficher les détails de la requête (démo)",
           "own_only": "Les clients ne voient que leurs propres comptes.",
           "details": "Détails de la requête", "status": "Statut", "parser": "Analyseur", "attempts": "tentatives",
           "intent": "Intention", "params": "Paramètres", "written_by": "Réponse rédigée par",
           "answer_language": "Langue", "typos": "Fautes corrigées", "guard": "Problèmes détectés en sortie",
           "audit": "📋 Journal d'audit (responsable uniquement, 20 dernières entrées)", "no_entries": "Aucune entrée pour l'instant.",
           "dark": "🌙 Mode sombre", "light": "☀️ Mode clair",
           "manager": "Responsable", "employee": "Employé", "customer": "Client"},
    "ar": {"sign_in": "سجل الدخول للمتابعة", "new_chat": "محادثة جديدة", "search": "البحث في المحادثات", "recents": "الأخيرة",
           "no_conversations": "لا توجد محادثات بعد.", "chatting_as": "تتحدث بصفتك", "begin": "من أين نبدأ؟",
           "disclaimer": "تأتي الإجابات فقط من قاعدة بيانات البنك. وككل ذكاء اصطناعي، قد يخطئ.", "settings": "الإعدادات",
           "ask": "اطرح سؤالا عن البنك (اكتب «مساعدة» للأفكار)", "try": "جرب أن تسأل",
           "logout": "تسجيل الخروج", "role": "الدور", "thinking": "جار التفكير...", "language": "اللغة",
           "tagline": "مساعد مصرفي آمن. تأتي الإجابات فقط من استعلامات معتمدة للقراءة فقط.",
           "username": "اسم المستخدم", "password": "كلمة المرور", "login": "تسجيل الدخول",
           "demo": "حسابات تجريبية", "wrong_login": "اسم المستخدم أو كلمة المرور غير صحيحة.",
           "locked": "محاولات فاشلة كثيرة. يرجى المحاولة لاحقا.",
           "engine": "المحرك", "engine_fast": "سريع (مطابقة دلالية وإجابات جاهزة، بدون نموذج)",
           "engine_ai": "نموذج الذكاء الاصطناعي (تحليل Qwen وإجابات يكتبها النموذج)",
           "no_model": "لم يتم تنزيل نموذج Qwen بعد، لذا يتوفر المحرك السريع فقط.",
           "details_toggle": "عرض تفاصيل الاستعلام (تجريبي)", "own_only": "يمكن للعملاء رؤية حساباتهم فقط.",
           "details": "تفاصيل الاستعلام", "status": "الحالة", "parser": "المحلل", "attempts": "محاولات",
           "intent": "النية", "params": "المعلمات", "written_by": "كتب الإجابة",
           "answer_language": "اللغة", "typos": "أخطاء مصححة", "guard": "مشكلات فحص الإجابة",
           "audit": "📋 سجل التدقيق (للمدير فقط، آخر 20)", "no_entries": "لا توجد سجلات بعد.",
           "dark": "🌙 الوضع الداكن", "light": "☀️ الوضع الفاتح",
           "manager": "مدير", "employee": "موظف", "customer": "عميل"},
}


def _index(lang: str) -> int:
    return 0 if lang == "fr" else 1


def message(key: str, lang: str, **fields) -> str:
    """A translated message. English callers normally use the original constants."""
    if lang == "en":
        return _ENGLISH_MESSAGES[key].format(**fields)
    return _MESSAGES[key][_index(lang)].format(**fields)


def intent_text(name: str, lang: str) -> str:
    return INTENT_TEXT[name][_index(lang)]


def role_name(role: str, lang: str) -> str:
    return ROLES[role][_index(lang)]


def decision_message(code: str, lang: str, default: str, role: str | None = None,
                     intent: str | None = None) -> str:
    """Translate an RBAC refusal. The decision itself was already made in rbac.py."""
    if lang == "en" or code not in _MESSAGES:
        return default
    if code == "role_not_permitted":
        return message(code, lang, role=role_name(role, lang), what=intent_text(intent, lang).lower())
    return message(code, lang)


def period_label(label: str, lang: str) -> str:
    """Translate a DateRange label, keeping every number and date exactly as it is."""
    i = _index(lang)
    m = re.match(r"the last (\d+) (days|months) \((.*)\)$", label)
    if m:
        dates = m[3].replace(" to ", " au " if lang == "fr" else " إلى ")
        if lang == "fr":
            return f"les {m[1]} derniers {'jours' if m[2] == 'days' else 'mois'} ({dates})"
        return f"آخر {m[1]} {'يوما' if m[2] == 'days' else 'أشهر'} ({dates})"
    for name, translations in _MONTHS.items():
        label = label.replace(name, translations[i])
    for english, french, arabic in _PERIOD_WORDS:
        label = label.replace(english, french if lang == "fr" else arabic)
    return label


def translate_row(row: dict, lang: str) -> str:
    i = _index(lang)
    cells = []
    for column, value in row.items():
        name = COLUMNS.get(column, (column.replace("_", " "),) * 2)[i]
        shown = VALUES.get(value, (value,) * 2)[i] if isinstance(value, str) else value
        cells.append(f"{name} : {shown}" if lang == "fr" else f"{name}: {shown}")
    return ("، " if lang == "ar" else ", ").join(cells)


def format_result(result, lang: str) -> str:
    """The plain template answer in French or Arabic. Numbers are copied from the result."""
    period = message("period", lang, label=period_label(result.period.label, lang)) if result.period else ""
    if not result.rows:
        return message("no_records", lang, period=period)
    if len(result.rows) == 1:
        return message("according", lang, period=period, values=translate_row(result.rows[0], lang))
    lines = [message("according_list", lang, period=period)]
    lines += ["- " + translate_row(row, lang) for row in result.rows]
    return "\n".join(lines)
