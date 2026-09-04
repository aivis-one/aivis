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

    /* === CHART === */
    'chart.1w':           { ru: '1Н', en: '1W', de: '1W' },
    'chart.1m':           { ru: '1М', en: '1M', de: '1M' },
    'chart.3m':           { ru: '3М', en: '3M', de: '3M' },
    'chart.1y':           { ru: '1Г', en: '1Y', de: '1J' },
    'inv.chart.title':    { ru: 'Динамика портфеля', en: 'Portfolio Trend', de: 'Portfolioentwicklung' },
    'agent.chart.title':  { ru: 'Заработок', en: 'Earnings', de: 'Verdienst' },

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
    'nav.auth.verification': { ru: 'Верификация (внешняя)', en: 'Verification (external)', de: 'Verifizierung (extern)' },
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

    /* === INVESTOR — Transactions === */
    'inv.tx.deposit':       { ru: 'Пополнение USDT (TRC20)', en: 'Deposit USDT (TRC20)', de: 'Einzahlung USDT (TRC20)' },
    'inv.tx.deposit2':      { ru: 'Пополнение USDT (ERC20)', en: 'Deposit USDT (ERC20)', de: 'Einzahlung USDT (ERC20)' },
    'inv.tx.purchaseIpi':   { ru: 'Покупка IPI AG', en: 'Purchase IPI AG', de: 'Kauf IPI AG' },
    'inv.tx.purchaseIpi5k': { ru: 'Покупка IPI AG (5000 юн.)', en: 'Purchase IPI AG (5000 un.)', de: 'Kauf IPI AG (5000 Ant.)' },
    'inv.tx.purchaseImmo':  { ru: 'Покупка Immo-Pro-Invest', en: 'Purchase Immo-Pro-Invest', de: 'Kauf Immo-Pro-Invest' },
    'inv.tx.bankTransfer':  { ru: 'Банковский перевод', en: 'Bank Transfer', de: 'Banküberweisung' },
    'inv.tx.today':         { ru: 'Сегодня, 14:23', en: 'Today, 14:23', de: 'Heute, 14:23' },

    /* === INVESTOR — News === */
    'inv.news.ipiTitle':         { ru: 'IPI AG: новый этап строительства', en: 'IPI AG: new construction phase', de: 'IPI AG: neue Bauphase' },
    'inv.news.installmentTitle': { ru: 'Обновление условий рассрочки', en: 'Installment terms updated', de: 'Ratenbedingungen aktualisiert' },

    /* === INVESTOR — Documents content === */
    'inv.doc.agreementIpi':  { ru: 'Инвестиционное соглашение — IPI AG', en: 'Investment Agreement — IPI AG', de: 'Investitionsvereinbarung — IPI AG' },
    'inv.doc.agreementImmo': { ru: 'Инвестиционное соглашение — Immo-Pro-Invest', en: 'Investment Agreement — Immo-Pro-Invest', de: 'Investitionsvereinbarung — Immo-Pro-Invest' },
    'inv.doc.bonusCert':     { ru: 'Сертификат бонусных юнитов — IPI AG', en: 'Bonus Units Certificate — IPI AG', de: 'Bonusanteile-Zertifikat — IPI AG' },
    'inv.doc.userAgreement': { ru: 'Пользовательское соглашение cbshome.org', en: 'User Agreement cbshome.org', de: 'Nutzungsvereinbarung cbshome.org' },

    /* === INVESTOR — Installment table === */
    'inv.installment.now':   { ru: '1 (сейчас)', en: '1 (now)', de: '1 (jetzt)' },

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

    /* === COMPANY — Dashboard === */
    'comp.role':               { ru: 'Компания', en: 'Company', de: 'Unternehmen' },
    'comp.revenue':            { ru: 'Выручка', en: 'Revenue', de: 'Umsatz' },
    'comp.products':           { ru: 'Продукты', en: 'Products', de: 'Produkte' },
    'comp.monthlySales':       { ru: 'Продаж (мес)', en: 'Sales (month)', de: 'Verkäufe (Monat)' },
    'comp.passive':            { ru: 'Пассивный баланс', en: 'Passive Balance', de: 'Passives Guthaben' },
    'comp.lastTx':             { ru: 'Последние транзакции', en: 'Recent Transactions', de: 'Letzte Transaktionen' },
    'comp.allTx':              { ru: 'Все →', en: 'All →', de: 'Alle →' },
    'comp.products.title':     { ru: 'Продукты', en: 'Products', de: 'Produkte' },
    'comp.backProducts':       { ru: 'Продукты', en: 'Products', de: 'Produkte' },
    'comp.dist.company':       { ru: 'Компания', en: 'Company', de: 'Unternehmen' },
    'comp.dist.l1':            { ru: 'L1 агент', en: 'L1 Agent', de: 'L1 Agent' },
    'comp.dist.l2':            { ru: 'L2 агент', en: 'L2 Agent', de: 'L2 Agent' },
    'comp.dist.l3':            { ru: 'L3 агент', en: 'L3 Agent', de: 'L3 Agent' },
    'comp.salesByMonth':       { ru: 'Продажи по месяцам', en: 'Sales by Month', de: 'Verkäufe pro Monat' },
    'comp.badge':              { ru: 'Компания', en: 'Company', de: 'Unternehmen' },
    'comp.passive.label':      { ru: 'Пассивный баланс (выручка компании)', en: 'Passive Balance (company revenue)', de: 'Passives Guthaben (Unternehmensumsatz)' },

    /* === STAFF — Dashboard === */
    'staff.users.stat':        { ru: 'Пользователи', en: 'Users', de: 'Benutzer' },
    'staff.kycQueue':          { ru: 'KYC очередь', en: 'KYC Queue', de: 'KYC-Warteschlange' },
    'staff.pending':           { ru: 'Ожидают', en: 'Pending', de: 'Ausstehend' },
    'staff.payments.stat':     { ru: 'Платежи', en: 'Payments', de: 'Zahlungen' },
    'staff.awaitingConfirm':   { ru: 'Ожидают подтверждения', en: 'Awaiting Confirmation', de: 'Warten auf Bestätigung' },
    'staff.agentApps':         { ru: 'Заявки агентов', en: 'Agent Applications', de: 'Agentenanträge' },
    'staff.quickActions':      { ru: 'Быстрые действия', en: 'Quick Actions', de: 'Schnellaktionen' },
    'staff.processKyc':        { ru: 'Обработать KYC', en: 'Process KYC', de: 'KYC bearbeiten' },
    'staff.checkPayments':     { ru: 'Проверить платежи', en: 'Check Payments', de: 'Zahlungen prüfen' },
    'staff.users.title':       { ru: 'Пользователи', en: 'Users', de: 'Benutzer' },
    'staff.searchPlaceholder': { ru: 'Поиск по имени, email...', en: 'Search by name, email...', de: 'Suche nach Name, E-Mail...' },
    'staff.kyc.title':         { ru: 'KYC Очередь', en: 'KYC Queue', de: 'KYC-Warteschlange' },
    'staff.payments.title':    { ru: 'Платежи', en: 'Payments', de: 'Zahlungen' },
    'staff.agentApps.title':   { ru: 'Заявки агентов', en: 'Agent Applications', de: 'Agentenanträge' },

    /* === COMPANY — Dashboard extras === */
    'comp.admin':              { ru: 'Админ:', en: 'Admin:', de: 'Admin:' },
    'comp.revenue.change':     { ru: '+€42K за месяц', en: '+€42K this month', de: '+42K € diesen Monat' },
    'comp.products.active':    { ru: '2 активных', en: '2 active', de: '2 aktiv' },
    'comp.products.revShare':  { ru: '75% от выручки', en: '75% of revenue', de: '75 % des Umsatzes' },
    'comp.products.count':     { ru: '3 продукта', en: '3 products', de: '3 Produkte' },
    'comp.addProduct':         { ru: '+ Добавить', en: '+ Add', de: '+ Hinzufügen' },
    'comp.badge.active':       { ru: 'Активен', en: 'Active', de: 'Aktiv' },
    'comp.badge.hidden':       { ru: 'Скрыт', en: 'Hidden', de: 'Versteckt' },
    'comp.badge.archive':      { ru: 'Архив', en: 'Archive', de: 'Archiv' },
    'comp.perUnit':            { ru: '/ед.', en: '/unit', de: '/Ant.' },
    'comp.sold.347k':          { ru: '347K продано', en: '347K sold', de: '347K verkauft' },
    'comp.sold.128k':          { ru: '128K продано', en: '128K sold', de: '128K verkauft' },
    'comp.comingSoon':         { ru: 'Скоро', en: 'Coming Soon', de: 'Demnächst' },
    'comp.editHint':           { ru: 'Нажмите на продукт для редактирования. Распределение комиссий настраивается в карточке продукта.', en: 'Tap a product to edit. Commission distribution is configured in the product card.', de: 'Tippen Sie auf ein Produkt zum Bearbeiten. Die Provisionsverteilung wird in der Produktkarte konfiguriert.' },
    'comp.editing':            { ru: 'Редактирование', en: 'Edit', de: 'Bearbeiten' },
    'comp.form.name':          { ru: 'Название продукта', en: 'Product Name', de: 'Produktname' },
    'comp.form.desc':          { ru: 'Описание', en: 'Description', de: 'Beschreibung' },
    'comp.form.pricePerUnit':  { ru: 'Цена за единицу (€)', en: 'Price per unit (€)', de: 'Preis pro Einheit (€)' },
    'comp.form.status':        { ru: 'Статус', en: 'Status', de: 'Status' },
    'comp.dist.title':         { ru: 'Распределение комиссий', en: 'Commission Distribution', de: 'Provisionsverteilung' },
    'comp.dist.platform':      { ru: 'Платформа CBS HOME', en: 'CBS HOME Platform', de: 'CBS HOME Plattform' },
    'comp.dist.sumCheck':      { ru: 'Сумма: 75 + 10 + 3 + 1 + 11 = 100%', en: 'Sum: 75 + 10 + 3 + 1 + 11 = 100%', de: 'Summe: 75 + 10 + 3 + 1 + 11 = 100 %' },
    'comp.save':               { ru: 'Сохранить', en: 'Save', de: 'Speichern' },
    'comp.cancel':             { ru: 'Отмена', en: 'Cancel', de: 'Abbrechen' },

    /* === COMPANY — Analytics === */
    'comp.analytics.title':    { ru: 'Аналитика', en: 'Analytics', de: 'Analytik' },
    'comp.analytics.totalRev': { ru: 'Общая выручка', en: 'Total Revenue', de: 'Gesamtumsatz' },
    'comp.analytics.thisMonth':{ ru: 'Этот месяц', en: 'This month', de: 'Diesen Monat' },
    'comp.analytics.unitsSold':{ ru: 'Юнитов продано', en: 'Units sold', de: 'Anteile verkauft' },
    'comp.analytics.units':    { ru: 'юнитов', en: 'units', de: 'Anteile' },
    'comp.chart.label':        { ru: 'Окт — Апр 2026 (юниты)', en: 'Oct — Apr 2026 (units)', de: 'Okt — Apr 2026 (Anteile)' },
    'comp.month.oct':          { ru: 'Окт', en: 'Oct', de: 'Okt' },
    'comp.month.nov':          { ru: 'Ноя', en: 'Nov', de: 'Nov' },
    'comp.month.dec':          { ru: 'Дек', en: 'Dec', de: 'Dez' },
    'comp.month.jan':          { ru: 'Янв', en: 'Jan', de: 'Jan' },
    'comp.month.feb':          { ru: 'Фев', en: 'Feb', de: 'Feb' },
    'comp.month.mar':          { ru: 'Мар', en: 'Mar', de: 'Mär' },
    'comp.month.apr':          { ru: 'Апр', en: 'Apr', de: 'Apr' },
    'comp.topAgents':          { ru: 'Топ агенты', en: 'Top Agents', de: 'Top-Agenten' },
    'comp.topAgents.all':      { ru: 'Все →', en: 'All →', de: 'Alle →' },
    'comp.monthBreakdown':     { ru: 'Месячная разбивка', en: 'Monthly Breakdown', de: 'Monatsaufschlüsselung' },

    /* === COMPANY — Analytics data === */
    'comp.agent.volume.48200': { ru: '48 200 юнитов', en: '48,200 units', de: '48.200 Anteile' },
    'comp.agent.volume.41800': { ru: '41 800 юнитов', en: '41,800 units', de: '41.800 Anteile' },
    'comp.agent.volume.38500': { ru: '38 500 юнитов', en: '38,500 units', de: '38.500 Anteile' },
    'comp.agent.volume.32100': { ru: '32 100 юнитов', en: '32,100 units', de: '32.100 Anteile' },
    'comp.agent.volume.28700': { ru: '28 700 юнитов', en: '28,700 units', de: '28.700 Anteile' },
    'comp.breakdown.mar':      { ru: 'Март 2026', en: 'March 2026', de: 'März 2026' },
    'comp.breakdown.mar.d':    { ru: 'IPI: 28K + Immo: 14K юнитов', en: 'IPI: 28K + Immo: 14K units', de: 'IPI: 28K + Immo: 14K Anteile' },
    'comp.breakdown.feb':      { ru: 'Февраль 2026', en: 'February 2026', de: 'Februar 2026' },
    'comp.breakdown.feb.d':    { ru: 'IPI: 24K + Immo: 12K юнитов', en: 'IPI: 24K + Immo: 12K units', de: 'IPI: 24K + Immo: 12K Anteile' },
    'comp.breakdown.jan':      { ru: 'Январь 2026', en: 'January 2026', de: 'Januar 2026' },
    'comp.breakdown.jan.d':    { ru: 'IPI: 22K + Immo: 10K юнитов', en: 'IPI: 22K + Immo: 10K units', de: 'IPI: 22K + Immo: 10K Anteile' },

    /* === COMPANY — Transaction data === */
    'comp.tx.ipi5000':         { ru: 'IPI AG Shares — 5 000 ед.', en: 'IPI AG Shares — 5,000 un.', de: 'IPI AG Shares — 5.000 Ant.' },
    'comp.tx.immo3000':        { ru: 'Immo-Pro-Invest — 3 000 ед.', en: 'Immo-Pro-Invest — 3,000 un.', de: 'Immo-Pro-Invest — 3.000 Ant.' },
    'comp.tx.ipi8000':         { ru: 'IPI AG Shares — 8 000 ед.', en: 'IPI AG Shares — 8,000 un.', de: 'IPI AG Shares — 8.000 Ant.' },
    'comp.tx.petrova':         { ru: 'Анна Петрова \u2022 L1 агент', en: 'Anna Petrova \u2022 L1 Agent', de: 'Anna Petrowa \u2022 L1 Agent' },
    'comp.tx.kozlov':          { ru: 'Дмитрий Козлов \u2022 L2 агент', en: 'Dmitry Kozlov \u2022 L2 Agent', de: 'Dmitri Koslow \u2022 L2 Agent' },
    'comp.tx.morozova':        { ru: 'Елена Морозова \u2022 L1 агент', en: 'Elena Morozova \u2022 L1 Agent', de: 'Elena Morosowa \u2022 L1 Agent' },

    /* === COMPANY — Settings === */
    'comp.settings.title':     { ru: 'Настройки', en: 'Settings', de: 'Einstellungen' },
    'comp.settings.admin':     { ru: 'Администратор', en: 'Administrator', de: 'Administrator' },
    'comp.settings.verified':  { ru: 'Верифицирована', en: 'Verified', de: 'Verifiziert' },
    'comp.settings.confirmed': { ru: 'Подтверждён', en: 'Confirmed', de: 'Bestätigt' },
    'comp.settings.compProfile':{ ru: 'Профиль компании', en: 'Company Profile', de: 'Unternehmensprofil' },
    'comp.settings.name':      { ru: 'Название', en: 'Name', de: 'Name' },
    'comp.settings.desc':      { ru: 'Описание', en: 'Description', de: 'Beschreibung' },
    'comp.settings.descVal':   { ru: 'Инвестиционный холдинг', en: 'Investment holding', de: 'Investmentholding' },
    'comp.settings.legalAddr': { ru: 'Юр. адрес', en: 'Legal Address', de: 'Rechtsadresse' },
    'comp.settings.docs':      { ru: 'Документы', en: 'Documents', de: 'Dokumente' },
    'comp.settings.license':   { ru: 'Лицензия', en: 'License', de: 'Lizenz' },
    'comp.settings.uploaded':  { ru: 'Загружена', en: 'Uploaded', de: 'Hochgeladen' },
    'comp.settings.charter':   { ru: 'Устав', en: 'Charter', de: 'Satzung' },
    'comp.settings.charterVal':{ ru: 'Загружен', en: 'Uploaded', de: 'Hochgeladen' },
    'comp.settings.kyb':       { ru: 'KYB верификация', en: 'KYB Verification', de: 'KYB-Verifizierung' },
    'comp.settings.kybVal':    { ru: 'Пройдена', en: 'Completed', de: 'Abgeschlossen' },
    'comp.settings.withdrawal':{ ru: 'Вывод средств', en: 'Withdrawal', de: 'Auszahlung' },
    'comp.settings.bankDetails':{ ru: 'Банковские реквизиты', en: 'Bank Details', de: 'Bankverbindung' },
    'comp.settings.history':   { ru: 'История выводов', en: 'Withdrawal History', de: 'Auszahlungsverlauf' },
    'comp.settings.historyVal':{ ru: '12 операций', en: '12 transactions', de: '12 Transaktionen' },
    'comp.settings.withdraw':  { ru: 'Вывести', en: 'Withdraw', de: 'Auszahlen' },
    'comp.settings.reinvest':  { ru: 'Реинвест', en: 'Reinvest', de: 'Reinvestieren' },
    'comp.settings.logout':    { ru: 'Выйти', en: 'Log Out', de: 'Abmelden' },

    /* === COMPANY — Product description data === */
    'comp.productDesc':        { ru: 'Инвестиционные паи IPI AG. Минимальная покупка — 100 юнитов. Доход формируется из прибыли холдинга.', en: 'IPI AG investment units. Minimum purchase — 100 units. Income from holding profits.', de: 'IPI AG Investmentanteile. Mindestkauf — 100 Anteile. Erträge aus Holdinggewinnen.' },

    /* === STAFF — Dashboard extras === */
    'staff.users.change':      { ru: '+34 за месяц', en: '+34 this month', de: '+34 diesen Monat' },
    'staff.new':               { ru: 'Новые', en: 'New', de: 'Neu' },
    'staff.role.investor':     { ru: 'Инвестор', en: 'Investor', de: 'Investor' },
    'staff.role.agent':        { ru: 'Агент', en: 'Agent', de: 'Agent' },
    'staff.role.company':      { ru: 'Компания', en: 'Company', de: 'Unternehmen' },
    'staff.kyc.hint':          { ru: 'Проверьте документы и данные пользователя перед одобрением. Среднее время обработки: 15 мин.', en: 'Review documents and user data before approval. Average processing time: 15 min.', de: 'Prüfen Sie Dokumente und Nutzerdaten vor der Genehmigung. Durchschnittliche Bearbeitungszeit: 15 Min.' },
    'staff.kyc.passportRF':    { ru: 'Паспорт РФ', en: 'Russian Passport', de: 'Russischer Pass' },
    'staff.kyc.submitted':     { ru: 'Подан', en: 'Submitted', de: 'Eingereicht' },
    'staff.kyc.moreApps':      { ru: '... ещё 9 заявок', en: '... 9 more applications', de: '... 9 weitere Anträge' },
    'staff.payments.hint':     { ru: 'Проверьте хеш транзакции в блокчейне перед подтверждением. Все платежи — крипто (USDT).', en: 'Verify the transaction hash on the blockchain before confirming. All payments are crypto (USDT).', de: 'Überprüfen Sie den Transaktionshash in der Blockchain vor der Bestätigung. Alle Zahlungen sind Krypto (USDT).' },
    'staff.more.title':        { ru: 'Ещё', en: 'More', de: 'Mehr' },
    'staff.settings.tools':    { ru: 'Инструменты', en: 'Tools', de: 'Werkzeuge' },
    'staff.settings.system':   { ru: 'Система', en: 'System', de: 'System' },
    'staff.settings.platform': { ru: 'Платформа', en: 'Platform', de: 'Plattform' },
    'staff.settings.language': { ru: 'Язык', en: 'Language', de: 'Sprache' },
    'staff.settings.langVal':  { ru: 'Русский', en: 'English', de: 'Deutsch' },

    /* === STAFF — Agent Applications === */
    'staff.agentApps.hint':    { ru: 'Инвестор может подать заявку на статус агента. Cooldown: 30 дней после отклонения. Проверьте историю инвестиций.', en: 'An investor can apply for agent status. Cooldown: 30 days after rejection. Review investment history.', de: 'Ein Investor kann den Agentenstatus beantragen. Cooldown: 30 Tage nach Ablehnung. Prüfen Sie die Investitionshistorie.' },
    'staff.agentApps.since':   { ru: 'Инвестор с', en: 'Investor since', de: 'Investor seit' },
    'staff.agentApps.portfolio':{ ru: 'Портфель:', en: 'Portfolio:', de: 'Portfolio:' },
    'staff.agentApps.purchases5':{ ru: '5 покупок', en: '5 purchases', de: '5 Käufe' },
    'staff.agentApps.purchases3':{ ru: '3 покупки', en: '3 purchases', de: '3 Käufe' },
    'staff.agentApps.purchases2':{ ru: '2 покупки', en: '2 purchases', de: '2 Käufe' },
    'staff.agentApps.cooldown':{ ru: 'Cooldown закончился 15.03', en: 'Cooldown ended 15.03', de: 'Cooldown endete 15.03' },

    /* === STAFF — Avatar Mode === */
    'staff.avatar.title':      { ru: 'Режим аватара', en: 'Avatar Mode', de: 'Avatar-Modus' },
    'staff.avatar.subtitle':   { ru: 'Просматривайте платформу глазами пользователя', en: 'View the platform as the user sees it', de: 'Sehen Sie die Plattform aus Nutzersicht' },
    'staff.avatar.selectUser': { ru: 'Выберите пользователя', en: 'Select user', de: 'Benutzer auswählen' },
    'staff.avatar.portfolio':  { ru: 'портфель', en: 'portfolio', de: 'Portfolio' },
    'staff.avatar.referrals':  { ru: 'рефералов', en: 'referrals', de: 'Empfehlungen' },
    'staff.avatar.restrictions':{ ru: 'Ограниченные операции в Avatar Mode', en: 'Restricted operations in Avatar Mode', de: 'Eingeschränkte Operationen im Avatar-Modus' },
    'staff.avatar.noPurchase': { ru: 'Нельзя совершать покупки от имени пользователя', en: 'Cannot make purchases on behalf of the user', de: 'Keine Käufe im Namen des Nutzers möglich' },
    'staff.avatar.noWithdraw': { ru: 'Нельзя выводить средства', en: 'Cannot withdraw funds', de: 'Keine Auszahlungen möglich' },
    'staff.avatar.noPassword': { ru: 'Нельзя менять пароль или email', en: 'Cannot change password or email', de: 'Passwort oder E-Mail nicht änderbar' },
    'staff.avatar.noDelete':   { ru: 'Нельзя удалять аккаунт', en: 'Cannot delete account', de: 'Konto kann nicht gelöscht werden' },
    'staff.avatar.noKyc':      { ru: 'Нельзя менять KYC данные', en: 'Cannot modify KYC data', de: 'KYC-Daten nicht änderbar' },
    'staff.avatar.session':    { ru: 'Активная сессия', en: 'Active Session', de: 'Aktive Sitzung' },

    /* === STAFF — User detail data === */
    'staff.user.petrova.detail':  { ru: 'Инвестор \u2022 anna@mail.ru', en: 'Investor \u2022 anna@mail.ru', de: 'Investor \u2022 anna@mail.ru' },
    'staff.user.seider.detail':   { ru: 'Агент \u2022 sergej@cbshome.org', en: 'Agent \u2022 sergej@cbshome.org', de: 'Agent \u2022 sergej@cbshome.org' },
    'staff.user.ivanov.detail':   { ru: 'Инвестор \u2022 max.iv@gmail.com', en: 'Investor \u2022 max.iv@gmail.com', de: 'Investor \u2022 max.iv@gmail.com' },
    'staff.user.immoag.detail':   { ru: 'Компания \u2022 info@immo-ag.de', en: 'Company \u2022 info@immo-ag.de', de: 'Unternehmen \u2022 info@immo-ag.de' },
    'staff.user.sidorova.detail': { ru: 'Инвестор \u2022 nat.sid@yandex.ru', en: 'Investor \u2022 nat.sid@yandex.ru', de: 'Investor \u2022 nat.sid@yandex.ru' },
    'staff.user.hoffmann.detail': { ru: 'Агент \u2022 klaus@cbshome.org', en: 'Agent \u2022 klaus@cbshome.org', de: 'Agent \u2022 klaus@cbshome.org' },
    'staff.user.morozov.detail':  { ru: 'Инвестор \u2022 ilya.m@outlook.com', en: 'Investor \u2022 ilya.m@outlook.com', de: 'Investor \u2022 ilya.m@outlook.com' },
    'staff.user.erstekapital.detail':{ ru: 'Компания \u2022 ek@erste-kapital.de', en: 'Company \u2022 ek@erste-kapital.de', de: 'Unternehmen \u2022 ek@erste-kapital.de' },

    /* === STAFF — KYC data === */
    'staff.kyc.ivanov':        { ru: 'Инвестор \u2022 Паспорт РФ \u2022 Подан 28.03.2026', en: 'Investor \u2022 Russian Passport \u2022 Submitted 28.03.2026', de: 'Investor \u2022 Russischer Pass \u2022 Eingereicht 28.03.2026' },
    'staff.kyc.erstekapital':  { ru: 'Компания \u2022 Handelsregister \u2022 Подан 30.03.2026', en: 'Company \u2022 Handelsregister \u2022 Submitted 30.03.2026', de: 'Unternehmen \u2022 Handelsregister \u2022 Eingereicht 30.03.2026' },
    'staff.kyc.schmidt':       { ru: 'Инвестор \u2022 Personalausweis \u2022 Подан 01.04.2026', en: 'Investor \u2022 Personalausweis \u2022 Submitted 01.04.2026', de: 'Investor \u2022 Personalausweis \u2022 Eingereicht 01.04.2026' },

    /* === STAFF — Avatar detail data === */
    'staff.avatar.petrova':    { ru: 'Инвестор \u2022 €24 750 портфель', en: 'Investor \u2022 €24,750 portfolio', de: 'Investor \u2022 24.750 € Portfolio' },
    'staff.avatar.seider':     { ru: 'Агент \u2022 47 рефералов', en: 'Agent \u2022 47 referrals', de: 'Agent \u2022 47 Empfehlungen' },
    'staff.avatar.ivanov':     { ru: 'Инвестор \u2022 €48 200 портфель', en: 'Investor \u2022 €48,200 portfolio', de: 'Investor \u2022 48.200 € Portfolio' },

    /* === STAFF — Agent app detail data === */
    'staff.agentApp.morozov.1':  { ru: 'Инвестор с 2024 \u2022 Портфель: €18 400', en: 'Investor since 2024 \u2022 Portfolio: €18,400', de: 'Investor seit 2024 \u2022 Portfolio: 18.400 €' },
    'staff.agentApp.morozov.2':  { ru: '5 покупок \u2022 KYC', en: '5 purchases \u2022 KYC', de: '5 Käufe \u2022 KYC' },
    'staff.agentApp.kozlova.1':  { ru: 'Инвестор с 2025 \u2022 Портфель: €8 100', en: 'Investor since 2025 \u2022 Portfolio: €8,100', de: 'Investor seit 2025 \u2022 Portfolio: 8.100 €' },
    'staff.agentApp.kozlova.2':  { ru: '3 покупки \u2022 KYC', en: '3 purchases \u2022 KYC', de: '3 Käufe \u2022 KYC' },
    'staff.agentApp.schneider.1':{ ru: 'Инвестор с 2025 \u2022 Портфель: €4 200', en: 'Investor since 2025 \u2022 Portfolio: €4,200', de: 'Investor seit 2025 \u2022 Portfolio: 4.200 €' },
    'staff.agentApp.schneider.2':{ ru: '2 покупки \u2022 KYC', en: '2 purchases \u2022 KYC', de: '2 Käufe \u2022 KYC' },
    'staff.agentApp.schneider.3':{ ru: 'Cooldown закончился 15.03', en: 'Cooldown ended 15.03', de: 'Cooldown endete 15.03' },

    /* === AUTH — Placeholders === */
    'auth.login.passPlaceholder':    { ru: 'Введите пароль', en: 'Enter password', de: 'Passwort eingeben' },
    'auth.register.passPlaceholder': { ru: 'Минимум 8 символов', en: 'Minimum 8 characters', de: 'Mindestens 8 Zeichen' },
    'auth.register.confirmPlaceholder':{ ru: 'Повторите пароль', en: 'Repeat password', de: 'Passwort wiederholen' },

    /* === AUTH — Select options (data content, skip i18n in HTML but provide keys for JS) === */
    'auth.profile.countryRu':     { ru: 'Россия', en: 'Russia', de: 'Russland' },
    'auth.profile.countryOther':  { ru: 'Другая', en: 'Other', de: 'Andere' },
    'auth.profile.langRu':        { ru: 'Русский', en: 'Russian', de: 'Russisch' },

    /* === AUTH — JS strings === */
    'auth.role.continueAs':        { ru: 'Продолжить как', en: 'Continue as', de: 'Weiter als' },
    'auth.docs.signDocumentsBtn':  { ru: 'Подписать документы', en: 'Sign Documents', de: 'Dokumente unterschreiben' },
    'auth.docs.checkedOf':         { ru: 'Отмечено {checked} из {total}', en: 'Checked {checked} of {total}', de: '{checked} von {total} markiert' },

    /* === AGENT — Commission data === */
    'agent.units':               { ru: 'юнитов', en: 'units', de: 'Anteile' },
    'agent.unitsShort':          { ru: 'юн.', en: 'un.', de: 'Ant.' },
    'agent.comm.l1label':        { ru: 'Комиссия L1', en: 'Commission L1', de: 'Provision L1' },
    'agent.comm.l2label':        { ru: 'Комиссия L2', en: 'Commission L2', de: 'Provision L2' },
    'agent.bonusTop20':          { ru: 'Бонус Top-20 (март)', en: 'Top-20 Bonus (March)', de: 'Top-20 Bonus (März)' },
    'agent.monthlyPool':         { ru: 'Месячный пул 2%', en: 'Monthly pool 2%', de: 'Monatspool 2 %' },
    'agent.coolingOff':          { ru: 'Cooling-off (14д)', en: 'Cooling-off (14d)', de: 'Cooling-off (14T)' },
    'agent.frozenDays':          { ru: '❄️ 14д', en: '❄️ 14d', de: '❄️ 14T' },

    /* === AGENT — Dashboard comm data === */
    'agent.comm.petrova':        { ru: 'Анна Петрова', en: 'Anna Petrova', de: 'Anna Petrowa' },
    'agent.comm.petrova.p':      { ru: 'IPI AG \u00B7 5 000 юнитов', en: 'IPI AG \u00B7 5,000 units', de: 'IPI AG \u00B7 5.000 Anteile' },
    'agent.comm.kozlov':         { ru: 'Дмитрий Козлов', en: 'Dmitry Kozlov', de: 'Dmitri Koslow' },
    'agent.comm.kozlov.p':       { ru: 'Immo-Pro-Invest \u00B7 3 000 юн.', en: 'Immo-Pro-Invest \u00B7 3,000 un.', de: 'Immo-Pro-Invest \u00B7 3.000 Ant.' },
    'agent.comm.morozova':       { ru: 'Елена Морозова', en: 'Elena Morozova', de: 'Elena Morosowa' },
    'agent.comm.morozova.p':     { ru: 'IPI AG \u00B7 2 000 юнитов', en: 'IPI AG \u00B7 2,000 units', de: 'IPI AG \u00B7 2.000 Anteile' },
    'agent.comm.novikov':        { ru: 'Алексей Новиков', en: 'Alexey Novikov', de: 'Alexej Nowikow' },
    'agent.comm.novikov.p':      { ru: 'CBS Home \u00B7 10 000 юнитов', en: 'CBS Home \u00B7 10,000 units', de: 'CBS Home \u00B7 10.000 Anteile' },
    'agent.comm.volkova':        { ru: 'Мария Волкова', en: 'Maria Volkova', de: 'Maria Wolkowa' },
    'agent.comm.volkova.p':      { ru: 'IPI AG \u00B7 1 000 юнитов', en: 'IPI AG \u00B7 1,000 units', de: 'IPI AG \u00B7 1.000 Anteile' },
    'agent.comm.sokolov':        { ru: 'Кирилл Соколов', en: 'Kirill Sokolov', de: 'Kirill Sokolow' },
    'agent.comm.sokolov.p':      { ru: 'Immo-Pro-Invest \u00B7 5 000 юн.', en: 'Immo-Pro-Invest \u00B7 5,000 un.', de: 'Immo-Pro-Invest \u00B7 5.000 Ant.' },
    'agent.comm.lebedeva':       { ru: 'Ольга Лебедева', en: 'Olga Lebedeva', de: 'Olga Lebedewa' },
    'agent.comm.lebedeva.p':     { ru: 'IPI AG \u00B7 8 000 юнитов', en: 'IPI AG \u00B7 8,000 units', de: 'IPI AG \u00B7 8.000 Anteile' },
    'agent.comm.popov':          { ru: 'Сергей Попов', en: 'Sergey Popov', de: 'Sergej Popow' },
    'agent.comm.popov.p':        { ru: 'IPI AG \u00B7 18 000 юнитов', en: 'IPI AG \u00B7 18,000 units', de: 'IPI AG \u00B7 18.000 Anteile' },

    /* === AGENT — Leaderboard data === */
    'agent.lb.ivanov':           { ru: 'Максим Иванов', en: 'Maxim Ivanov', de: 'Maxim Iwanow' },
    'agent.lb.ivanov.v':         { ru: '€48 200 объём', en: '€48,200 volume', de: '48.200 € Volumen' },
    'agent.lb.sidorova':         { ru: 'Наталья Сидорова', en: 'Natalia Sidorova', de: 'Natalja Sidorowa' },
    'agent.lb.sidorova.v':       { ru: '€41 800 объём', en: '€41,800 volume', de: '41.800 € Volumen' },
    'agent.lb.volkov':           { ru: 'Артём Волков', en: 'Artem Volkov', de: 'Artjom Wolkow' },
    'agent.lb.volkov.v':         { ru: '€38 500 объём', en: '€38,500 volume', de: '38.500 € Volumen' },
    'agent.lb.seider.v':         { ru: '€18 420 объём', en: '€18,420 volume', de: '18.420 € Volumen' },
    'agent.lb.morozov':          { ru: 'Илья Морозов', en: 'Ilya Morozov', de: 'Ilja Morosow' },
    'agent.lb.morozov.v':        { ru: '€8 900 объём', en: '€8,900 volume', de: '8.900 € Volumen' },
    'agent.lb.kozlova':          { ru: 'Татьяна Козлова', en: 'Tatiana Kozlova', de: 'Tatjana Koslowa' },
    'agent.lb.kozlova.v':        { ru: '€8 100 объём', en: '€8,100 volume', de: '8.100 € Volumen' },

    /* === AGENT — Passive balance data === */
    'agent.passive.commL1':      { ru: 'Комиссия L1 — Петрова', en: 'Commission L1 — Petrova', de: 'Provision L1 — Petrowa' },
    'agent.passive.commL2':      { ru: 'Комиссия L2 — Козлов', en: 'Commission L2 — Kozlov', de: 'Provision L2 — Koslow' },
    'agent.passive.bonusTop20':  { ru: 'Бонус Top-20 (март)', en: 'Top-20 Bonus (March)', de: 'Top-20 Bonus (März)' },
    'agent.passive.monthlyPool': { ru: 'Месячный пул 2%', en: 'Monthly pool 2%', de: 'Monatspool 2 %' },

    /* === INVESTOR — Product description (JS data) === */
    'inv.product.desc.ipi':    { ru: 'Инвестиционные юниты IPI AG обеспечены портфелем строительных проектов в Германии. Патентованная технология CBS HOME (EP 3 574 160 B1) обеспечивает конкурентное преимущество: строительство в 6-9 раз быстрее традиционных методов при экономии 15-20% на материалах.', en: 'IPI AG investment units are backed by a portfolio of construction projects in Germany. The patented CBS HOME technology (EP 3 574 160 B1) provides a competitive advantage: construction 6-9x faster than traditional methods with 15-20% material savings.', de: 'IPI AG Investmentanteile sind durch ein Portfolio von Bauprojekten in Deutschland abgesichert. Die patentierte CBS HOME Technologie (EP 3 574 160 B1) bietet einen Wettbewerbsvorteil: 6-9x schnelleres Bauen als traditionelle Methoden bei 15-20 % Materialeinsparung.' },
    'inv.product.desc.immo':   { ru: 'Инвестиции в портфель объектов недвижимости через Immo-Pro-Invest GmbH. Профессиональное управление активами с фокусом на стабильный рост стоимости и диверсификацию.', en: 'Investments in a real estate portfolio via Immo-Pro-Invest GmbH. Professional asset management focused on stable value growth and diversification.', de: 'Investitionen in ein Immobilienportfolio über Immo-Pro-Invest GmbH. Professionelles Asset Management mit Fokus auf stabiles Wertwachstum und Diversifikation.' },
    'inv.product.desc.cbs':    { ru: 'Франшиза CBS Home — инновационная строительная технология Compound Building System. Запатентованная система (58 стран), единственное допущение DIBt Z-14.5-883. Производственная мощность: 120-190 м²/день.', en: 'CBS Home franchise — innovative Compound Building System construction technology. Patented system (58 countries), sole DIBt Z-14.5-883 approval. Production capacity: 120-190 m²/day.', de: 'CBS Home Franchise — innovative Compound Building System Bautechnologie. Patentiertes System (58 Länder), einzige DIBt Z-14.5-883 Zulassung. Produktionskapazität: 120-190 m²/Tag.' },

    /* === INVESTOR — Purchase flow data === */
    'inv.purchase.product.ipi':  { ru: 'IPI AG Shares — €1.00 / юнит', en: 'IPI AG Shares — €1.00 / unit', de: 'IPI AG Shares — 1,00 € / Anteil' },
    'inv.purchase.bonusUnits':   { ru: '+500 юнитов', en: '+500 units', de: '+500 Anteile' },
    'inv.purchase.confirmBtn':   { ru: 'Подтвердить покупку', en: 'Confirm Purchase', de: 'Kauf bestätigen' },
    'inv.purchase.done.text':    { ru: 'IPI AG Shares — 5 000 юнитов = €5 000', en: 'IPI AG Shares — 5,000 units = €5,000', de: 'IPI AG Shares — 5.000 Anteile = 5.000 €' },
    'inv.installment.confirmBtn':{ ru: 'Оформить рассрочку', en: 'Start Installment', de: 'Ratenzahlung starten' },
    'inv.bonusCalc':             { ru: 'юнитов', en: 'units', de: 'Anteile' },
    'inv.bonusNone':             { ru: 'Нет (мин. 5 000)', en: 'None (min. 5,000)', de: 'Keine (min. 5.000)' },

    /* === INVESTOR — Document meta === */
    'inv.doc.meta.ipi1':       { ru: 'Подписан 28.03.2026 — 5 000 юнитов', en: 'Signed 28.03.2026 — 5,000 units', de: 'Unterschrieben 28.03.2026 — 5.000 Anteile' },
    'inv.doc.meta.immo1':      { ru: 'Подписан 20.03.2026 — 5 000 юнитов', en: 'Signed 20.03.2026 — 5,000 units', de: 'Unterschrieben 20.03.2026 — 5.000 Anteile' },
    'inv.doc.meta.bonus1':     { ru: 'Выдан 28.03.2026 — 500 юнитов', en: 'Issued 28.03.2026 — 500 units', de: 'Ausgestellt 28.03.2026 — 500 Anteile' },
    'inv.doc.meta.agreement1': { ru: 'Подписан 15.03.2026', en: 'Signed 15.03.2026', de: 'Unterschrieben 15.03.2026' },

    /* === INVESTOR — Balance frozen timer === */
    'inv.balance.frozenMin':   { ru: '59 мин', en: '59 min', de: '59 Min' },
    'inv.balance.until':       { ru: 'До 02.04.2026', en: 'Until 02.04.2026', de: 'Bis 02.04.2026' },
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
