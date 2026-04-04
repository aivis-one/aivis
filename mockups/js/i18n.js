/* ========== I18N SYSTEM ==========
   livemockup-studio v1.8.0 — CBS HOME
   Locales: ru, en, de
   Persist: localStorage('cbs-lang')
   ========== */

const I18N = {
  _locale: 'ru',
  _key: 'cbs-lang',
  _locales: ['ru', 'en', 'de'],

  _dict: {
    /* === THEME === */
    'theme.auto':  { ru: 'Тема: Авто', en: 'Theme: Auto', de: 'Design: Auto' },
    'theme.light': { ru: 'Тема: Светлая', en: 'Theme: Light', de: 'Design: Hell' },
    'theme.dark':  { ru: 'Тема: Тёмная', en: 'Theme: Dark', de: 'Design: Dunkel' },

    /* === NAVIGATION MAP === */
    'nav.map.title':     { ru: 'Карта навигации', en: 'Navigation Map', de: 'Navigationskarte' },
    'nav.map.screens':   { ru: 'экранов', en: 'screens', de: 'Bildschirme' },
    'nav.map.paths':     { ru: 'полных путей', en: 'paths', de: 'Pfade' },
    'nav.map.endpoints': { ru: 'финальных точек', en: 'endpoints', de: 'Endpunkte' },
    'nav.legend.screen':   { ru: 'Экран', en: 'Screen', de: 'Bildschirm' },
    'nav.legend.tab':      { ru: 'Табы', en: 'Tabs', de: 'Tabs' },
    'nav.legend.endpoint': { ru: 'Финальная точка', en: 'Dead end', de: 'Endpunkt' },

    /* === NAVIGATION TOASTS === */
    'nav.endpoint': { ru: '📌 {name} — финальная точка', en: '📌 {name} — endpoint', de: '📌 {name} — Endpunkt' },
    'nav.tab':      { ru: '🟡 Таб "{name}" — переключает контент', en: '🟡 Tab "{name}" — switches content', de: '🟡 Tab "{name}" — wechselt Inhalt' },

    /* === NAV MAP SECTIONS (shared) === */
    'nav.section.auth':       { ru: 'АУТЕНТИФИКАЦИЯ', en: 'AUTHENTICATION', de: 'AUTHENTIFIZIERUNG' },
    'nav.section.onboarding': { ru: 'ОНБОРДИНГ', en: 'ONBOARDING', de: 'ONBOARDING' },
    'nav.section.tabs':       { ru: 'ТАБЫ', en: 'TABS', de: 'TABS' },
    'nav.section.purchase':   { ru: 'ПОКУПКА', en: 'PURCHASE', de: 'KAUF' },
    'nav.section.documents':  { ru: 'ДОКУМЕНТЫ', en: 'DOCUMENTS', de: 'DOKUMENTE' },
    'nav.section.endpoints':  { ru: 'ФИНАЛЬНЫЕ ТОЧКИ', en: 'ENDPOINTS', de: 'ENDPUNKTE' },
    'nav.section.agent_hub':  { ru: 'HUB АГЕНТА', en: 'AGENT HUB', de: 'AGENTEN-HUB' },
    'nav.section.management': { ru: 'УПРАВЛЕНИЕ', en: 'MANAGEMENT', de: 'VERWALTUNG' },

    /* === NAV MAP — auth-flow === */
    'nav.auth.login':    { ru: 'Вход', en: 'Login', de: 'Anmeldung' },
    'nav.auth.register': { ru: 'Регистрация', en: 'Register', de: 'Registrierung' },
    'nav.auth.verify':   { ru: 'Подтверждение Email', en: 'Email Verification', de: 'E-Mail-Verifizierung' },
    'nav.auth.telegram': { ru: 'Вход через Telegram', en: 'Telegram Login', de: 'Telegram-Anmeldung' },
    'nav.auth.forgot':   { ru: 'Забыли пароль', en: 'Forgot Password', de: 'Passwort vergessen' },
    'nav.auth.profile':  { ru: 'Настройка профиля', en: 'Profile Setup', de: 'Profil einrichten' },
    'nav.auth.role':     { ru: 'Выбор роли', en: 'Role Selection', de: 'Rollenwahl' },
    'nav.auth.kyc':      { ru: 'Верификация KYC', en: 'KYC Verification', de: 'KYC-Verifizierung' },
    'nav.auth.sumsub':   { ru: 'SumSub (внешний)', en: 'SumSub (external)', de: 'SumSub (extern)' },
    'nav.auth.docs':     { ru: 'Подписание документов', en: 'Document Signing', de: 'Dokumentenunterzeichnung' },
    'nav.auth.complete': { ru: 'Онбординг завершён', en: 'Onboarding Complete', de: 'Onboarding abgeschlossen' },

    /* === NAV MAP — investor === */
    'nav.inv.dashboard':      { ru: 'Главная', en: 'Dashboard', de: 'Dashboard' },
    'nav.inv.portfolio':      { ru: 'Портфель', en: 'Portfolio', de: 'Portfolio' },
    'nav.inv.marketplace':    { ru: 'Маркетплейс', en: 'Marketplace', de: 'Marktplatz' },
    'nav.inv.productDetail':  { ru: 'Детали продукта', en: 'Product Detail', de: 'Produktdetails' },
    'nav.inv.purchase':       { ru: '↳ Покупка', en: '↳ Purchase', de: '↳ Kauf' },
    'nav.inv.purchaseDone':   { ru: '↳ Покупка выполнена', en: '↳ Purchase Complete', de: '↳ Kauf abgeschlossen' },
    'nav.inv.installment':    { ru: '↳ Рассрочка', en: '↳ Installment', de: '↳ Ratenzahlung' },
    'nav.inv.installmentDone':{ ru: '↳ Рассрочка оформлена', en: '↳ Installment Done', de: '↳ Ratenzahlung abgeschlossen' },
    'nav.inv.balance':        { ru: 'Баланс', en: 'Balance', de: 'Kontostand' },
    'nav.inv.documents':      { ru: 'Документы', en: 'Documents', de: 'Dokumente' },
    'nav.inv.docView':        { ru: '↳ Просмотр документа', en: '↳ Document View', de: '↳ Dokumentansicht' },
    'nav.inv.settings':       { ru: 'Настройки', en: 'Settings', de: 'Einstellungen' },
    'nav.inv.notifications':  { ru: 'Уведомления', en: 'Notifications', de: 'Benachrichtigungen' },
    'nav.inv.newsItem':       { ru: 'Новость', en: 'News Item', de: 'Nachricht' },
    'nav.inv.agentRequest':   { ru: 'Заявка на роль агента', en: 'Agent Role Request', de: 'Agentenrolle beantragen' },
    'nav.inv.companyDetails': { ru: 'Детали по компании', en: 'Company Details', de: 'Unternehmensdetails' },
    'nav.inv.txDetails':      { ru: 'Детали транзакции', en: 'Transaction Details', de: 'Transaktionsdetails' },
    'nav.inv.logout':         { ru: 'Выход из аккаунта', en: 'Logout', de: 'Abmelden' },

    /* === NAV MAP — agent === */
    'nav.agent.dashboard':    { ru: 'Главная', en: 'Dashboard', de: 'Dashboard' },
    'nav.agent.hub':          { ru: 'Hub Агента', en: 'Agent Hub', de: 'Agenten-Hub' },
    'nav.agent.commissions':  { ru: 'Комиссии', en: 'Commissions', de: 'Provisionen' },
    'nav.agent.passive':      { ru: 'Пассивный баланс', en: 'Passive Balance', de: 'Passives Guthaben' },
    'nav.agent.settings':     { ru: 'Настройки', en: 'Settings', de: 'Einstellungen' },
    'nav.agent.referrals':    { ru: 'Реферальные ссылки', en: 'Referral Links', de: 'Empfehlungslinks' },
    'nav.agent.leaderboard':  { ru: 'Лидерборд', en: 'Leaderboard', de: 'Rangliste' },

    /* === NAV MAP — company === */
    'nav.comp.dashboard':     { ru: 'Главная', en: 'Dashboard', de: 'Dashboard' },
    'nav.comp.products':      { ru: 'Продукты', en: 'Products', de: 'Produkte' },
    'nav.comp.analytics':     { ru: 'Аналитика', en: 'Analytics', de: 'Analytik' },
    'nav.comp.balance':       { ru: 'Баланс', en: 'Balance', de: 'Kontostand' },
    'nav.comp.settings':      { ru: 'Настройки', en: 'Settings', de: 'Einstellungen' },
    'nav.comp.product_edit':  { ru: 'Редактирование продукта', en: 'Product Edit', de: 'Produkt bearbeiten' },

    /* === NAV MAP — staff === */
    'nav.staff.dashboard':    { ru: 'Главная', en: 'Dashboard', de: 'Dashboard' },
    'nav.staff.users':        { ru: 'Пользователи', en: 'Users', de: 'Benutzer' },
    'nav.staff.kyc':          { ru: 'KYC Очередь', en: 'KYC Queue', de: 'KYC-Warteschlange' },
    'nav.staff.payments':     { ru: 'Проверка платежей', en: 'Payment Review', de: 'Zahlungsprüfung' },
    'nav.staff.more':         { ru: 'Ещё', en: 'More', de: 'Mehr' },
    'nav.staff.agent_apps':   { ru: 'Заявки агентов', en: 'Agent Applications', de: 'Agentenanträge' },
    'nav.staff.avatar':       { ru: 'Режим аватара', en: 'Avatar Mode', de: 'Avatar-Modus' },

    /* === TAB BAR — investor === */
    'tab.home':       { ru: 'Главная', en: 'Home', de: 'Start' },
    'tab.portfolio':  { ru: 'Портфель', en: 'Portfolio', de: 'Portfolio' },
    'tab.market':     { ru: 'Маркет', en: 'Market', de: 'Markt' },
    'tab.balance':    { ru: 'Баланс', en: 'Balance', de: 'Kontostand' },
    'tab.more':       { ru: 'Ещё', en: 'More', de: 'Mehr' },

    /* === TAB BAR — agent === */
    'tab.agent.home':        { ru: 'Главная', en: 'Home', de: 'Start' },
    'tab.agent.hub':         { ru: 'Hub', en: 'Hub', de: 'Hub' },
    'tab.agent.commissions': { ru: 'Комиссии', en: 'Commissions', de: 'Provisionen' },
    'tab.agent.balance':     { ru: 'Баланс', en: 'Balance', de: 'Kontostand' },
    'tab.agent.more':        { ru: 'Ещё', en: 'More', de: 'Mehr' },

    /* === TAB BAR — company === */
    'tab.comp.home':      { ru: 'Главная', en: 'Home', de: 'Start' },
    'tab.comp.products':  { ru: 'Продукты', en: 'Products', de: 'Produkte' },
    'tab.comp.analytics': { ru: 'Аналитика', en: 'Analytics', de: 'Analytik' },
    'tab.comp.balance':   { ru: 'Баланс', en: 'Balance', de: 'Kontostand' },
    'tab.comp.settings':  { ru: 'Настройки', en: 'Settings', de: 'Einstellungen' },

    /* === TAB BAR — staff === */
    'tab.staff.home':     { ru: 'Главная', en: 'Home', de: 'Start' },
    'tab.staff.users':    { ru: 'Пользователи', en: 'Users', de: 'Benutzer' },
    'tab.staff.kyc':      { ru: 'KYC', en: 'KYC', de: 'KYC' },
    'tab.staff.payments': { ru: 'Платежи', en: 'Payments', de: 'Zahlungen' },
    'tab.staff.more':     { ru: 'Ещё', en: 'More', de: 'Mehr' },

    /* === AUTH FLOW — Login === */
    'auth.login.title':         { ru: 'Вход в аккаунт', en: 'Sign In', de: 'Anmelden' },
    'auth.login.subtitle':      { ru: 'Войдите в CBS HOME для управления инвестициями', en: 'Sign in to CBS HOME to manage your investments', de: 'Melden Sie sich bei CBS HOME an, um Ihre Investitionen zu verwalten' },
    'auth.login.email':         { ru: 'Email', en: 'Email', de: 'E-Mail' },
    'auth.login.password':      { ru: 'Пароль', en: 'Password', de: 'Passwort' },
    'auth.login.forgot':        { ru: 'Забыли пароль?', en: 'Forgot password?', de: 'Passwort vergessen?' },
    'auth.login.btn':           { ru: 'Войти', en: 'Sign In', de: 'Anmelden' },
    'auth.login.or':            { ru: 'или', en: 'or', de: 'oder' },
    'auth.login.telegram':      { ru: 'Войти через Telegram', en: 'Sign in with Telegram', de: 'Mit Telegram anmelden' },
    'auth.login.noAccount':     { ru: 'Нет аккаунта?', en: 'No account?', de: 'Kein Konto?' },
    'auth.login.createAccount': { ru: 'Создать аккаунт', en: 'Create account', de: 'Konto erstellen' },
    'auth.back':                { ru: 'Назад', en: 'Back', de: 'Zurück' },

    /* === AUTH FLOW — Register === */
    'auth.register.title':           { ru: 'Создать аккаунт', en: 'Create Account', de: 'Konto erstellen' },
    'auth.register.subtitle':        { ru: 'Присоединяйтесь к инвестиционной платформе CBS HOME', en: 'Join the CBS HOME investment platform', de: 'Werden Sie Teil der CBS HOME Investitionsplattform' },
    'auth.register.email':           { ru: 'Email', en: 'Email', de: 'E-Mail' },
    'auth.register.password':        { ru: 'Пароль', en: 'Password', de: 'Passwort' },
    'auth.register.passwordHint':    { ru: 'Минимум 8 символов, буквы и цифры', en: 'Minimum 8 characters, letters and numbers', de: 'Mindestens 8 Zeichen, Buchstaben und Zahlen' },
    'auth.register.confirmPassword': { ru: 'Подтверждение пароля', en: 'Confirm password', de: 'Passwort bestätigen' },
    'auth.register.terms':           { ru: 'Я принимаю', en: 'I accept the', de: 'Ich akzeptiere die' },
    'auth.register.btn':             { ru: 'Создать аккаунт', en: 'Create Account', de: 'Konto erstellen' },
    'auth.register.hasAccount':      { ru: 'Уже есть аккаунт?', en: 'Already have an account?', de: 'Haben Sie bereits ein Konto?' },
    'auth.register.loginLink':       { ru: 'Войти', en: 'Sign in', de: 'Anmelden' },

    /* === AUTH FLOW — Verify === */
    'auth.verify.title':    { ru: 'Проверьте почту', en: 'Check Your Email', de: 'Prüfen Sie Ihre E-Mail' },
    'auth.verify.subtitle': { ru: 'Мы отправили код подтверждения на', en: 'We sent a verification code to', de: 'Wir haben einen Bestätigungscode gesendet an' },
    'auth.verify.btn':      { ru: 'Подтвердить', en: 'Verify', de: 'Bestätigen' },
    'auth.verify.noCode':   { ru: 'Не получили код?', en: "Didn't receive the code?", de: 'Keinen Code erhalten?' },
    'auth.verify.resend':   { ru: 'Отправить повторно', en: 'Resend code', de: 'Code erneut senden' },

    /* === AUTH FLOW — Profile === */
    'auth.profile.title':     { ru: 'Данные профиля', en: 'Profile Setup', de: 'Profil einrichten' },
    'auth.profile.subtitle':  { ru: 'Заполните информацию для вашего аккаунта', en: 'Fill in your account information', de: 'Füllen Sie Ihre Kontoinformationen aus' },
    'auth.profile.firstName': { ru: 'Имя', en: 'First Name', de: 'Vorname' },
    'auth.profile.lastName':  { ru: 'Фамилия', en: 'Last Name', de: 'Nachname' },
    'auth.profile.phone':     { ru: 'Телефон', en: 'Phone', de: 'Telefon' },
    'auth.profile.country':   { ru: 'Страна', en: 'Country', de: 'Land' },
    'auth.profile.language':  { ru: 'Язык интерфейса', en: 'Interface Language', de: 'Sprache der Oberfläche' },
    'auth.profile.btn':       { ru: 'Продолжить', en: 'Continue', de: 'Weiter' },

    /* === AUTH FLOW — Role === */
    'auth.role.title':       { ru: 'Выберите роль', en: 'Choose Your Role', de: 'Wählen Sie Ihre Rolle' },
    'auth.role.subtitle':    { ru: 'Как вы планируете использовать платформу?', en: 'How do you plan to use the platform?', de: 'Wie möchten Sie die Plattform nutzen?' },
    'auth.role.investor':    { ru: 'Инвестор', en: 'Investor', de: 'Investor' },
    'auth.role.investorDesc':{ ru: 'Покупайте продукты, управляйте портфелем и отслеживайте инвестиции', en: 'Buy products, manage your portfolio and track investments', de: 'Produkte kaufen, Portfolio verwalten und Investitionen verfolgen' },
    'auth.role.agent':       { ru: 'Агент', en: 'Agent', de: 'Agent' },
    'auth.role.agentDesc':   { ru: 'Все возможности инвестора плюс реферальная программа и комиссии', en: 'All investor features plus referral program and commissions', de: 'Alle Investorfunktionen plus Empfehlungsprogramm und Provisionen' },
    'auth.role.company':     { ru: 'Компания', en: 'Company', de: 'Unternehmen' },
    'auth.role.companyDesc': { ru: 'Размещайте продукты, управляйте продажами и получайте выручку', en: 'List products, manage sales and earn revenue', de: 'Produkte listen, Verkäufe verwalten und Umsatz erzielen' },
    'auth.role.btn':         { ru: 'Выберите роль', en: 'Select a role', de: 'Rolle auswählen' },

    /* === AUTH FLOW — Role features === */
    'auth.role.feat.portfolio':     { ru: 'Портфель', en: 'Portfolio', de: 'Portfolio' },
    'auth.role.feat.installments':  { ru: 'Рассрочки', en: 'Installments', de: 'Ratenzahlung' },
    'auth.role.feat.balance':       { ru: 'Баланс', en: 'Balance', de: 'Kontostand' },
    'auth.role.feat.documents':     { ru: 'Документы', en: 'Documents', de: 'Dokumente' },
    'auth.role.feat.referrals':     { ru: 'Реферальные ссылки', en: 'Referral Links', de: 'Empfehlungslinks' },
    'auth.role.feat.commissions':   { ru: 'Комиссии L1/L2/L3', en: 'Commissions L1/L2/L3', de: 'Provisionen L1/L2/L3' },
    'auth.role.feat.leaderboard':   { ru: 'Лидерборд', en: 'Leaderboard', de: 'Rangliste' },
    'auth.role.feat.certification': { ru: 'Сертификация', en: 'Certification', de: 'Zertifizierung' },
    'auth.role.feat.products':      { ru: 'Продукты', en: 'Products', de: 'Produkte' },
    'auth.role.feat.analytics':     { ru: 'Аналитика', en: 'Analytics', de: 'Analytik' },
    'auth.role.feat.revenue':       { ru: 'Выручка', en: 'Revenue', de: 'Umsatz' },

    /* === AUTH FLOW — KYC === */
    'auth.kyc.title':          { ru: 'Верификация личности', en: 'Identity Verification', de: 'Identitätsprüfung' },
    'auth.kyc.subtitle':       { ru: 'Для работы на платформе необходимо пройти KYC-верификацию', en: 'KYC verification is required to use the platform', de: 'KYC-Verifizierung ist erforderlich, um die Plattform zu nutzen' },
    'auth.kyc.approved':       { ru: 'Верификация пройдена', en: 'Verification Complete', de: 'Verifizierung abgeschlossen' },
    'auth.kyc.approvedText':   { ru: 'Ваша личность подтверждена. Вы можете продолжить настройку аккаунта.', en: 'Your identity has been verified. You can continue setting up your account.', de: 'Ihre Identität wurde bestätigt. Sie können die Kontoeinrichtung fortsetzen.' },
    'auth.kyc.continue':       { ru: 'Продолжить', en: 'Continue', de: 'Weiter' },
    'auth.kyc.redo':           { ru: 'Пройти заново', en: 'Try again', de: 'Erneut versuchen' },
    'auth.kyc.statusesTitle':  { ru: 'Статусы верификации:', en: 'Verification statuses:', de: 'Verifizierungsstatus:' },
    'auth.kyc.statusPending':  { ru: 'Ожидание — документы на проверке', en: 'Pending — documents under review', de: 'Ausstehend — Dokumente werden geprüft' },
    'auth.kyc.statusApproved': { ru: 'Одобрено — верификация пройдена', en: 'Approved — verification complete', de: 'Genehmigt — Verifizierung abgeschlossen' },
    'auth.kyc.statusRejected': { ru: 'Отклонено — требуется повторная подача', en: 'Rejected — resubmission required', de: 'Abgelehnt — erneute Einreichung erforderlich' },

    /* === AUTH FLOW — Documents === */
    'auth.docs.title':         { ru: 'Подписание документов', en: 'Document Signing', de: 'Dokumentenunterzeichnung' },
    'auth.docs.subtitle':      { ru: 'Ознакомьтесь и подпишите обязательные документы для начала работы', en: 'Review and sign the required documents to get started', de: 'Prüfen und unterschreiben Sie die erforderlichen Dokumente' },
    'auth.docs.agreement':     { ru: 'Пользовательское соглашение cbshome.org', en: 'User Agreement cbshome.org', de: 'Nutzungsvereinbarung cbshome.org' },
    'auth.docs.agreementDesc': { ru: 'Основные условия использования платформы, права и обязанности сторон', en: 'Terms of use, rights and obligations of the parties', de: 'Nutzungsbedingungen, Rechte und Pflichten der Parteien' },
    'auth.docs.required':      { ru: 'Обязательный документ', en: 'Required document', de: 'Pflichtdokument' },
    'auth.docs.privacy':       { ru: 'Политика конфиденциальности', en: 'Privacy Policy', de: 'Datenschutzrichtlinie' },
    'auth.docs.privacyDesc':   { ru: 'Порядок обработки, хранения и защиты персональных данных в соответствии с GDPR', en: 'Processing, storage and protection of personal data under GDPR', de: 'Verarbeitung, Speicherung und Schutz personenbezogener Daten gemäß DSGVO' },
    'auth.docs.consent':       { ru: 'Согласие на обработку персональных данных', en: 'Consent to Personal Data Processing', de: 'Einwilligung zur Verarbeitung personenbezogener Daten' },
    'auth.docs.consentDesc':   { ru: 'Явное согласие на обработку ваших данных для предоставления услуг платформы', en: 'Explicit consent to process your data for platform services', de: 'Ausdrückliche Einwilligung zur Datenverarbeitung für Plattformdienste' },
    'auth.docs.signBtn':       { ru: 'Подписать документы', en: 'Sign Documents', de: 'Dokumente unterschreiben' },
    'auth.docs.signNote':      { ru: 'Нажимая «Подписать», вы соглашаетесь с условиями всех перечисленных документов', en: 'By clicking "Sign", you agree to the terms of all listed documents', de: 'Mit Klick auf „Unterschreiben" stimmen Sie den Bedingungen aller aufgeführten Dokumente zu' },

    /* === INVESTOR — Dashboard === */
    'inv.dashboard.welcome':         { ru: 'Добро пожаловать,', en: 'Welcome,', de: 'Willkommen,' },
    'inv.dashboard.portfolio':       { ru: 'Портфель', en: 'Portfolio', de: 'Portfolio' },
    'inv.dashboard.portfolioChange': { ru: '+12.4% за месяц', en: '+12.4% this month', de: '+12,4 % diesen Monat' },
    'inv.dashboard.activeBalance':   { ru: 'Активный баланс', en: 'Active Balance', de: 'Aktives Guthaben' },
    'inv.dashboard.confirmed':       { ru: 'Подтверждён', en: 'Confirmed', de: 'Bestätigt' },
    'inv.dashboard.frozen':          { ru: 'Заморожен', en: 'Frozen', de: 'Eingefroren' },
    'inv.dashboard.lastOps':         { ru: 'Последние операции', en: 'Recent Transactions', de: 'Letzte Transaktionen' },
    'inv.dashboard.allOps':          { ru: 'Все →', en: 'All →', de: 'Alle →' },
    'inv.dashboard.news':            { ru: 'Новости', en: 'News', de: 'Nachrichten' },

    /* === INVESTOR — Status badges === */
    'inv.status.frozen':    { ru: 'Заморожен', en: 'Frozen', de: 'Eingefroren' },
    'inv.status.confirmed': { ru: 'Подтверждён', en: 'Confirmed', de: 'Bestätigt' },

    /* === INVESTOR — News tags === */
    'inv.news.product':  { ru: 'Продукт', en: 'Product', de: 'Produkt' },
    'inv.news.platform': { ru: 'Платформа', en: 'Platform', de: 'Plattform' },

    /* === INVESTOR — Portfolio === */
    'inv.portfolio.totalValue': { ru: 'Общая стоимость портфеля', en: 'Total Portfolio Value', de: 'Gesamtportfoliowert' },
    'inv.portfolio.products':   { ru: 'Продуктов', en: 'Products', de: 'Produkte' },
    'inv.portfolio.units':      { ru: 'Юнитов', en: 'Units', de: 'Anteile' },
    'inv.portfolio.profit':     { ru: 'Прибыль', en: 'Profit', de: 'Gewinn' },
    'inv.portfolio.avgPrice':   { ru: 'Ср. цена', en: 'Avg Price', de: 'Ø Preis' },
    'inv.portfolio.value':      { ru: 'Стоимость', en: 'Value', de: 'Wert' },

    /* === INVESTOR — Market === */
    'inv.market.title':    { ru: 'Маркетплейс', en: 'Marketplace', de: 'Marktplatz' },
    'inv.market.subtitle': { ru: 'Доступные инвестиционные продукты', en: 'Available Investment Products', de: 'Verfügbare Investitionsprodukte' },
    'inv.market.ipiDesc':  { ru: 'Инвестиции в строительные проекты IPI AG. Доходность через рост стоимости юнитов.', en: 'Investments in IPI AG construction projects. Returns through unit value growth.', de: 'Investitionen in Bauprojekte der IPI AG. Rendite durch Wertsteigerung der Anteile.' },
    'inv.market.immoDesc': { ru: 'Инвестиции в недвижимость через Immo-Pro-Invest GmbH. Стабильный рост портфеля.', en: 'Real estate investments via Immo-Pro-Invest GmbH. Stable portfolio growth.', de: 'Immobilieninvestitionen über Immo-Pro-Invest GmbH. Stabiles Portfoliowachstum.' },
    'inv.market.cbsDesc':  { ru: 'Франшиза CBS Home — инновационная строительная технология. Запатентованная система.', en: 'CBS Home franchise — innovative construction technology. Patented system.', de: 'CBS Home Franchise — innovative Bautechnologie. Patentiertes System.' },
    'inv.unit':            { ru: 'юнит', en: 'unit', de: 'Anteil' },
    'inv.available':       { ru: 'доступно', en: 'available', de: 'verfügbar' },
    'inv.back':            { ru: 'Назад', en: 'Back', de: 'Zurück' },

    /* === INVESTOR — Product detail === */
    'inv.detail.pricePerUnit': { ru: 'Цена / юнит', en: 'Price / unit', de: 'Preis / Anteil' },
    'inv.detail.available':    { ru: 'Доступно', en: 'Available', de: 'Verfügbar' },
    'inv.detail.sixMonths':    { ru: 'За 6 мес', en: '6 months', de: '6 Monate' },
    'inv.detail.investors':    { ru: 'Инвесторов', en: 'Investors', de: 'Investoren' },
    'inv.detail.about':        { ru: 'О продукте', en: 'About', de: 'Über das Produkt' },
    'inv.detail.bonus':        { ru: 'Бонусные юниты', en: 'Bonus Units', de: 'Bonusanteile' },
    'inv.detail.bonusText':    { ru: 'При покупке от 5 000 юнитов — бонус +500 юнитов бесплатно.', en: 'When purchasing 5,000+ units — bonus +500 units free.', de: 'Ab 5.000 Anteilen — Bonus +500 Anteile gratis.' },
    'inv.detail.buy':          { ru: 'Купить', en: 'Buy', de: 'Kaufen' },
    'inv.detail.installment':  { ru: 'Рассрочка', en: 'Installment', de: 'Ratenzahlung' },

    /* === INVESTOR — Purchase === */
    'inv.purchase.title':        { ru: 'Покупка юнитов', en: 'Purchase Units', de: 'Anteile kaufen' },
    'inv.purchase.product':      { ru: 'Продукт', en: 'Product', de: 'Produkt' },
    'inv.purchase.quantity':     { ru: 'Количество юнитов', en: 'Number of units', de: 'Anzahl Anteile' },
    'inv.purchase.yourBalance':  { ru: 'Ваш активный баланс', en: 'Your active balance', de: 'Ihr aktives Guthaben' },
    'inv.purchase.units':        { ru: 'Юнитов', en: 'Units', de: 'Anteile' },
    'inv.purchase.pricePerUnit': { ru: 'Цена за юнит', en: 'Price per unit', de: 'Preis pro Anteil' },
    'inv.purchase.bonus':        { ru: 'Бонус', en: 'Bonus', de: 'Bonus' },
    'inv.purchase.total':        { ru: 'Итого', en: 'Total', de: 'Gesamt' },
    'inv.purchase.confirm':      { ru: 'Подтвердить покупку', en: 'Confirm Purchase', de: 'Kauf bestätigen' },

    /* === INVESTOR — Installment === */
    'inv.installment.title':       { ru: 'Рассрочка', en: 'Installment Plan', de: 'Ratenzahlungsplan' },
    'inv.installment.choosePlan':  { ru: 'Выберите план', en: 'Choose a plan', de: 'Plan auswählen' },
    'inv.installment.6months':     { ru: '6 месяцев', en: '6 months', de: '6 Monate' },
    'inv.installment.6monthsDesc': { ru: '10% x 5 платежей + 50% финальный. Бонус инвестору при завершении.', en: '10% x 5 payments + 50% final. Bonus on completion.', de: '10 % x 5 Zahlungen + 50 % Schlusszahlung. Bonus bei Abschluss.' },
    'inv.installment.12months':    { ru: '12 месяцев', en: '12 months', de: '12 Monate' },
    'inv.installment.12monthsDesc':{ ru: '5% x 11 платежей + 45% финальный. Увеличенный бонус при завершении.', en: '5% x 11 payments + 45% final. Increased bonus on completion.', de: '5 % x 11 Zahlungen + 45 % Schlusszahlung. Erhöhter Bonus bei Abschluss.' },
    'inv.installment.month':       { ru: 'Месяц', en: 'Month', de: 'Monat' },
    'inv.installment.amount':      { ru: 'Сумма', en: 'Amount', de: 'Betrag' },
    'inv.installment.unitsCol':    { ru: 'Юнитов', en: 'Units', de: 'Anteile' },
    'inv.installment.notice':      { ru: 'Цена фиксируется при оформлении. Первый платёж списывается сразу с активного баланса.', en: 'Price is locked at purchase. First payment is deducted from active balance immediately.', de: 'Preis wird beim Kauf fixiert. Erste Zahlung wird sofort vom aktiven Guthaben abgebucht.' },
    'inv.installment.confirm':     { ru: 'Оформить рассрочку', en: 'Start Installment', de: 'Ratenzahlung starten' },

    /* === INVESTOR — Balance === */
    'inv.balance.active':  { ru: 'Активный баланс', en: 'Active Balance', de: 'Aktives Guthaben' },
    'inv.balance.deposit': { ru: 'Пополнить (Crypto)', en: 'Deposit (Crypto)', de: 'Einzahlen (Crypto)' },
    'inv.balance.history': { ru: 'История операций', en: 'Transaction History', de: 'Transaktionsverlauf' },

    /* === INVESTOR — Documents === */
    'inv.docs.title':  { ru: 'Документы', en: 'Documents', de: 'Dokumente' },
    'inv.docs.issued': { ru: 'Выдан', en: 'Issued', de: 'Ausgestellt' },
    'inv.docs.signed': { ru: 'Подписан', en: 'Signed', de: 'Unterschrieben' },

    /* === INVESTOR — Settings === */
    'inv.settings.title':         { ru: 'Настройки', en: 'Settings', de: 'Einstellungen' },
    'inv.settings.profile':       { ru: 'Профиль', en: 'Profile', de: 'Profil' },
    'inv.settings.name':          { ru: 'Имя', en: 'Name', de: 'Name' },
    'inv.settings.verified':      { ru: 'Верифицирован', en: 'Verified', de: 'Verifiziert' },
    'inv.settings.phone':         { ru: 'Телефон', en: 'Phone', de: 'Telefon' },
    'inv.settings.country':       { ru: 'Страна', en: 'Country', de: 'Land' },
    'inv.settings.language':      { ru: 'Язык', en: 'Language', de: 'Sprache' },
    'inv.settings.notifications': { ru: 'Уведомления', en: 'Notifications', de: 'Benachrichtigungen' },
    'inv.settings.emailNotif':    { ru: 'Уведомления Email', en: 'Email Notifications', de: 'E-Mail-Benachrichtigungen' },
    'inv.settings.telegramNotif': { ru: 'Уведомления Telegram', en: 'Telegram Notifications', de: 'Telegram-Benachrichtigungen' },
    'inv.settings.roleInvestor':  { ru: 'Инвестор', en: 'Investor', de: 'Investor' },
    'inv.settings.actions':       { ru: 'Действия', en: 'Actions', de: 'Aktionen' },
    'inv.settings.becomeAgent':   { ru: 'Стать агентом', en: 'Become an Agent', de: 'Agent werden' },
    'inv.settings.myDocs':        { ru: 'Мои документы', en: 'My Documents', de: 'Meine Dokumente' },
    'inv.settings.logout':        { ru: 'Выйти', en: 'Log Out', de: 'Abmelden' },

    /* === AGENT — Dashboard === */
    'agent.role':              { ru: 'Агент', en: 'Agent', de: 'Agent' },
    'agent.referrals':         { ru: 'Рефералы', en: 'Referrals', de: 'Empfehlungen' },
    'agent.referrals.change':  { ru: '+5 за месяц', en: '+5 this month', de: '+5 diesen Monat' },
    'agent.commissions':       { ru: 'Комиссии', en: 'Commissions', de: 'Provisionen' },
    'agent.commissions.change':{ ru: '+€820 за месяц', en: '+€820 this month', de: '+€820 diesen Monat' },
    'agent.passive':           { ru: 'Пассивный баланс', en: 'Passive Balance', de: 'Passives Guthaben' },
    'agent.passive.sub':       { ru: 'Доступен для вывода', en: 'Available for withdrawal', de: 'Auszahlbar' },
    'agent.portfolio':         { ru: 'Портфель', en: 'Portfolio', de: 'Portfolio' },
    'agent.lastComm':          { ru: 'Последние комиссии', en: 'Recent Commissions', de: 'Letzte Provisionen' },
    'agent.all':               { ru: 'Все →', en: 'All →', de: 'Alle →' },
    'agent.today':             { ru: 'Сегодня', en: 'Today', de: 'Heute' },
    'agent.yesterday':         { ru: 'Вчера', en: 'Yesterday', de: 'Gestern' },

    /* === AGENT — Hub === */
    'agent.hub.title':         { ru: 'Hub Агента', en: 'Agent Hub', de: 'Agenten-Hub' },
    'agent.totalEarned':       { ru: 'Общий заработок', en: 'Total Earnings', de: 'Gesamtverdienst' },
    'agent.refLinks':          { ru: 'Реферальные ссылки', en: 'Referral Links', de: 'Empfehlungslinks' },
    'agent.active':            { ru: 'Активных', en: 'Active', de: 'Aktiv' },
    'agent.rank':              { ru: 'Ранг', en: 'Rank', de: 'Rang' },
    'agent.ofAgents':          { ru: 'из 156 агентов', en: 'of 156 agents', de: 'von 156 Agenten' },
    'agent.bonus':             { ru: 'Бонус (месяц)', en: 'Bonus (monthly)', de: 'Bonus (monatlich)' },
    'agent.certification':     { ru: 'Сертификация', en: 'Certification', de: 'Zertifizierung' },
    'agent.toGold':            { ru: 'До Gold: €1 580', en: 'To Gold: €1,580', de: 'Bis Gold: 1.580 €' },
    'agent.quickActions':      { ru: 'Быстрые действия', en: 'Quick Actions', de: 'Schnellaktionen' },
    'agent.createRef':         { ru: 'Создать реферальную ссылку', en: 'Create referral link', de: 'Empfehlungslink erstellen' },
    'agent.leaderboard':       { ru: 'Лидерборд', en: 'Leaderboard', de: 'Rangliste' },
    'agent.withdrawFunds':     { ru: 'Вывести средства', en: 'Withdraw funds', de: 'Auszahlen' },

    /* === AGENT — Referral Links === */
    'agent.refLinks.title':    { ru: 'Реферальные ссылки', en: 'Referral Links', de: 'Empfehlungslinks' },
    'agent.createNew':         { ru: 'Создать новую ссылку', en: 'Create new link', de: 'Neuen Link erstellen' },
    'agent.statusActive':      { ru: 'Активна', en: 'Active', de: 'Aktiv' },
    'agent.clicks':            { ru: 'Клики', en: 'Clicks', de: 'Klicks' },
    'agent.registrations':     { ru: 'Регистрации', en: 'Signups', de: 'Registrierungen' },
    'agent.purchases':         { ru: 'Покупки', en: 'Purchases', de: 'Käufe' },
    'agent.copyLink':          { ru: 'Копировать ссылку', en: 'Copy link', de: 'Link kopieren' },

    /* === AGENT — Commissions === */
    'agent.comm.title':        { ru: 'Комиссии', en: 'Commissions', de: 'Provisionen' },
    'agent.totalComm':         { ru: 'Общие комиссии', en: 'Total Commissions', de: 'Gesamtprovisionen' },
    'agent.thisMonth':         { ru: 'Этот месяц', en: 'This month', de: 'Diesen Monat' },
    'agent.lastMonth':         { ru: 'Прошлый', en: 'Last month', de: 'Letzter Monat' },
    'agent.filterAll':         { ru: 'Все', en: 'All', de: 'Alle' },

    /* === AGENT — Leaderboard === */
    'agent.leaderboard.title': { ru: 'Лидерборд', en: 'Leaderboard', de: 'Rangliste' },
    'agent.leaderboard.info':  { ru: 'Топ-20 делят 2% месячного пула. Топ-10 — дополнительно 1% квартального. Обновление каждые 60 мин.', en: 'Top 20 share 2% monthly pool. Top 10 — additional 1% quarterly. Updates every 60 min.', de: 'Top 20 teilen 2 % Monatspool. Top 10 — zusätzlich 1 % Quartalspool. Aktualisierung alle 60 Min.' },
    'agent.volume':            { ru: 'объём', en: 'volume', de: 'Volumen' },
    'agent.you':               { ru: '(вы)', en: '(you)', de: '(Sie)' },

    /* === AGENT — Passive Balance === */
    'agent.passive.title':     { ru: 'Пассивный баланс', en: 'Passive Balance', de: 'Passives Guthaben' },
    'agent.passive.label':     { ru: 'Пассивный баланс (заработок)', en: 'Passive Balance (earnings)', de: 'Passives Guthaben (Verdienst)' },
    'agent.confirmed':         { ru: 'Подтверждён', en: 'Confirmed', de: 'Bestätigt' },
    'agent.withdraw':          { ru: 'Вывести', en: 'Withdraw', de: 'Auszahlen' },
    'agent.toActive':          { ru: 'В активный', en: 'To Active', de: 'Auf Aktiv' },
    'agent.passive.info':      { ru: 'Пассивный баланс — это ваш заработок (комиссии, бонусы). Можно вывести (мин. €50) или перевести в активный баланс для покупок. Cooling-off период: 14 дней для EU fiat.', en: 'Passive balance is your earnings (commissions, bonuses). You can withdraw (min. €50) or transfer to active balance for purchases. Cooling-off period: 14 days for EU fiat.', de: 'Passives Guthaben sind Ihre Einnahmen (Provisionen, Boni). Auszahlung (min. 50 €) oder Transfer auf aktives Guthaben möglich. Cooling-off: 14 Tage für EU-Fiat.' },
    'agent.history':           { ru: 'История', en: 'History', de: 'Verlauf' },

    /* === AGENT — Settings === */
    'agent.settings.title':    { ru: 'Настройки', en: 'Settings', de: 'Einstellungen' },
    'agent.settings.agent':    { ru: 'АГЕНТ', en: 'AGENT', de: 'AGENT' },
    'agent.settings.rank':     { ru: 'Ранг', en: 'Rank', de: 'Rang' },
    'agent.settings.referrals':{ ru: 'Рефералов', en: 'Referrals', de: 'Empfehlungen' },
    'agent.settings.cert':     { ru: 'Сертификация', en: 'Certification', de: 'Zertifizierung' },
    'agent.settings.docs':     { ru: 'Документы агента', en: 'Agent Documents', de: 'Agenten-Dokumente' },
    'agent.settings.profile':  { ru: 'ПРОФИЛЬ', en: 'PROFILE', de: 'PROFIL' },
    'agent.settings.kyc':      { ru: 'Верифицирован', en: 'Verified', de: 'Verifiziert' },
    'agent.settings.lang':     { ru: 'Язык', en: 'Language', de: 'Sprache' },
    'agent.settings.logout':   { ru: 'Выйти', en: 'Log Out', de: 'Abmelden' },
  },

  init() {
    var saved = localStorage.getItem(this._key);
    if (this._locales.indexOf(saved) !== -1) {
      this._locale = saved;
    }
    this.applyI18n();
    this._updateSwitcher();
  },

  t(key, params) {
    var entry = this._dict[key];
    if (!entry) return key;
    var text = entry[this._locale] || entry.ru || key;
    if (params) {
      Object.keys(params).forEach(function(k) {
        text = text.replace('{' + k + '}', params[k]);
      });
    }
    return text;
  },

  setLocale(lang) {
    if (this._locales.indexOf(lang) === -1) return;
    this._locale = lang;
    localStorage.setItem(this._key, lang);
    this.applyI18n();
    this._updateSwitcher();
    document.documentElement.lang = lang;
    if (typeof showToast === 'function') {
      var names = { ru: 'Язык: Русский', en: 'Language: English', de: 'Sprache: Deutsch' };
      showToast(names[lang] || lang);
    }
  },

  toggleLocale() {
    var idx = this._locales.indexOf(this._locale);
    var next = this._locales[(idx + 1) % this._locales.length];
    this.setLocale(next);
  },

  applyI18n() {
    document.querySelectorAll('[data-i18n]').forEach(function(el) {
      var key = el.getAttribute('data-i18n');
      var attr = el.getAttribute('data-i18n-attr');
      var text = I18N.t(key);
      if (attr) {
        el.setAttribute(attr, text);
      } else {
        // Preserve child elements (like icons)
        var children = [];
        el.childNodes.forEach(function(n) {
          if (n.nodeType === 1) children.push(n); // Element nodes
        });
        if (children.length > 0 && el.querySelector('i, svg')) {
          // Has icon children — update only text nodes
          el.childNodes.forEach(function(n) {
            if (n.nodeType === 3 && n.textContent.trim()) n.textContent = text;
          });
        } else {
          el.textContent = text;
        }
      }
    });
    document.documentElement.lang = this._locale;
  },

  _updateSwitcher() {
    document.querySelectorAll('.lang-btn').forEach(function(btn) {
      btn.classList.toggle('active', btn.getAttribute('data-lang') === I18N._locale);
    });
  }
};
