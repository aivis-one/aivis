/* ========== I18N SYSTEM ==========
   livemockup-studio v1.6.0 — CBS HOME
   Locales: ru, en
   Persist: localStorage('cbs-lang')
   ========== */

const I18N = {
  _locale: 'ru',
  _key: 'cbs-lang',

  _dict: {
    /* === THEME === */
    'theme.auto':  { ru: 'Тема: Авто', en: 'Theme: Auto' },
    'theme.light': { ru: 'Тема: Светлая', en: 'Theme: Light' },
    'theme.dark':  { ru: 'Тема: Тёмная', en: 'Theme: Dark' },

    /* === NAVIGATION MAP === */
    'nav.map.title':     { ru: 'Карта навигации', en: 'Navigation Map' },
    'nav.map.screens':   { ru: 'экранов', en: 'screens' },
    'nav.map.paths':     { ru: 'путей', en: 'paths' },
    'nav.map.endpoints': { ru: 'финальных точек', en: 'endpoints' },
    'nav.legend.screen':   { ru: 'Экран', en: 'Screen' },
    'nav.legend.tab':      { ru: 'Табы', en: 'Tabs' },
    'nav.legend.endpoint': { ru: 'Тупик', en: 'Dead end' },

    /* === NAVIGATION TOASTS === */
    'nav.endpoint': { ru: '📌 {name} — финальная точка', en: '📌 {name} — endpoint' },
    'nav.tab':      { ru: '🟡 Таб "{name}" — переключает контент', en: '🟡 Tab "{name}" — switches content' },

    /* === TAB BAR === */
    'tab.home':       { ru: 'Главная', en: 'Home' },
    'tab.portfolio':  { ru: 'Портфель', en: 'Portfolio' },
    'tab.market':     { ru: 'Маркет', en: 'Market' },
    'tab.balance':    { ru: 'Баланс', en: 'Balance' },
    'tab.settings':   { ru: 'Ещё', en: 'More' },
    'tab.hub':        { ru: 'Hub', en: 'Hub' },
    'tab.commissions':{ ru: 'Комиссии', en: 'Commissions' },
    'tab.products':   { ru: 'Продукты', en: 'Products' },
    'tab.analytics':  { ru: 'Аналитика', en: 'Analytics' },
    'tab.users':      { ru: 'Пользователи', en: 'Users' },
    'tab.kyc':        { ru: 'KYC', en: 'KYC' },
    'tab.payments':   { ru: 'Платежи', en: 'Payments' },

    /* === AUTH FLOW === */
    'auth.login.title':     { ru: 'Вход в аккаунт', en: 'Sign In' },
    'auth.login.subtitle':  { ru: 'Войдите в CBS HOME для управления инвестициями', en: 'Sign in to CBS HOME to manage your investments' },
    'auth.login.btn':       { ru: 'Войти', en: 'Sign In' },
    'auth.login.telegram':  { ru: 'Войти через Telegram', en: 'Sign in with Telegram' },
    'auth.login.no_account':{ ru: 'Нет аккаунта?', en: 'No account?' },
    'auth.login.create':    { ru: 'Создать аккаунт', en: 'Create account' },
    'auth.login.forgot':    { ru: 'Забыли пароль?', en: 'Forgot password?' },
    'auth.register.title':  { ru: 'Создать аккаунт', en: 'Create Account' },
    'auth.register.subtitle':{ ru: 'Присоединяйтесь к инвестиционной платформе CBS HOME', en: 'Join the CBS HOME investment platform' },
    'auth.register.btn':    { ru: 'Создать аккаунт', en: 'Create Account' },
    'auth.register.has_account':{ ru: 'Уже есть аккаунт?', en: 'Already have an account?' },
    'auth.verify.title':    { ru: 'Проверьте почту', en: 'Check Your Email' },
    'auth.verify.subtitle': { ru: 'Мы отправили код подтверждения на', en: 'We sent a verification code to' },
    'auth.verify.btn':      { ru: 'Подтвердить', en: 'Verify' },
    'auth.verify.resend':   { ru: 'Отправить повторно', en: 'Resend code' },
    'auth.verify.no_code':  { ru: 'Не получили код?', en: "Didn't receive the code?" },
    'auth.profile.title':   { ru: 'Данные профиля', en: 'Profile Setup' },
    'auth.profile.subtitle':{ ru: 'Заполните информацию для вашего аккаунта', en: 'Fill in your account information' },
    'auth.profile.btn':     { ru: 'Продолжить', en: 'Continue' },
    'auth.role.title':      { ru: 'Выберите роль', en: 'Choose Your Role' },
    'auth.role.subtitle':   { ru: 'Как вы планируете использовать платформу?', en: 'How do you plan to use the platform?' },
    'auth.role.btn':        { ru: 'Выберите роль', en: 'Select a role' },
    'auth.kyc.title':       { ru: 'Верификация личности', en: 'Identity Verification' },
    'auth.kyc.subtitle':    { ru: 'Для работы на платформе необходимо пройти KYC-верификацию', en: 'KYC verification is required to use the platform' },
    'auth.kyc.approved':    { ru: 'Верификация пройдена', en: 'Verification Complete' },
    'auth.kyc.btn':         { ru: 'Продолжить', en: 'Continue' },
    'auth.docs.title':      { ru: 'Подписание документов', en: 'Document Signing' },
    'auth.docs.subtitle':   { ru: 'Ознакомьтесь и подпишите обязательные документы', en: 'Review and sign the required documents' },
    'auth.docs.btn':        { ru: 'Подписать документы', en: 'Sign Documents' },

    /* === COMMON === */
    'common.back':       { ru: 'Назад', en: 'Back' },
    'common.continue':   { ru: 'Продолжить', en: 'Continue' },
    'common.save':       { ru: 'Сохранить', en: 'Save' },
    'common.cancel':     { ru: 'Отмена', en: 'Cancel' },
    'common.confirm':    { ru: 'Подтвердить', en: 'Confirm' },
    'common.logout':     { ru: 'Выйти', en: 'Log Out' },
    'common.email':      { ru: 'Email', en: 'Email' },
    'common.password':   { ru: 'Пароль', en: 'Password' },
    'common.name':       { ru: 'Имя', en: 'First Name' },
    'common.surname':    { ru: 'Фамилия', en: 'Last Name' },
    'common.phone':      { ru: 'Телефон', en: 'Phone' },
    'common.country':    { ru: 'Страна', en: 'Country' },
    'common.language':   { ru: 'Язык интерфейса', en: 'Interface Language' },

    /* === FORM LABELS === */
    'form.required':     { ru: 'Обязательный документ', en: 'Required document' },
    'form.password_hint':{ ru: 'Минимум 8 символов, буквы и цифры', en: 'Minimum 8 characters, letters and numbers' },

    /* === INVESTOR === */
    'investor.welcome':     { ru: 'Добро пожаловать,', en: 'Welcome,' },
    'investor.portfolio':   { ru: 'Портфель', en: 'Portfolio' },
    'investor.active_balance':{ ru: 'Активный баланс', en: 'Active Balance' },
    'investor.frozen':      { ru: 'Заморожен', en: 'Frozen' },
    'investor.confirmed':   { ru: 'Подтверждён', en: 'Confirmed' },
    'investor.last_ops':    { ru: 'Последние операции', en: 'Recent Transactions' },
    'investor.all':         { ru: 'Все →', en: 'All →' },
    'investor.news':        { ru: 'Новости', en: 'News' },
    'investor.marketplace': { ru: 'Доступные инвестиционные продукты', en: 'Available Investment Products' },
    'investor.per_unit':    { ru: '/ юнит', en: '/ unit' },
    'investor.available':   { ru: 'доступно', en: 'available' },
    'investor.buy':         { ru: 'Купить', en: 'Buy' },
    'investor.installment': { ru: 'Рассрочка', en: 'Installment' },
    'investor.deposit':     { ru: '+ Пополнить (Crypto)', en: '+ Deposit (Crypto)' },
    'investor.history':     { ru: 'История операций', en: 'Transaction History' },
    'investor.total_value': { ru: 'Общая стоимость портфеля', en: 'Total Portfolio Value' },
    'investor.units':       { ru: 'Юнитов', en: 'Units' },
    'investor.avg_price':   { ru: 'Ср. цена', en: 'Avg Price' },
    'investor.value':       { ru: 'Стоимость', en: 'Value' },
    'investor.profit':      { ru: 'Прибыль', en: 'Profit' },
    'investor.products_count':{ ru: 'Продуктов', en: 'Products' },

    /* === AGENT === */
    'agent.rank':          { ru: 'Ранг', en: 'Rank' },
    'agent.referrals':     { ru: 'Рефералы', en: 'Referrals' },
    'agent.commissions':   { ru: 'Комиссии', en: 'Commissions' },
    'agent.passive':       { ru: 'Пассивный баланс', en: 'Passive Balance' },
    'agent.total_earned':  { ru: 'Общий заработок', en: 'Total Earnings' },
    'agent.ref_links':     { ru: 'Реферальные ссылки', en: 'Referral Links' },
    'agent.leaderboard':   { ru: 'Лидерборд', en: 'Leaderboard' },
    'agent.certification': { ru: 'Сертификация', en: 'Certification' },
    'agent.bonus':         { ru: 'Бонус (месяц)', en: 'Bonus (monthly)' },
    'agent.create_link':   { ru: '+ Создать новую ссылку', en: '+ Create new link' },
    'agent.copy_link':     { ru: 'Копировать ссылку', en: 'Copy link' },
    'agent.withdraw':      { ru: 'Вывести', en: 'Withdraw' },
    'agent.to_active':     { ru: '→ В активный', en: '→ To Active' },
    'agent.all_filter':    { ru: 'Все', en: 'All' },
    'agent.clicks':        { ru: 'Клики', en: 'Clicks' },
    'agent.registrations': { ru: 'Регистрации', en: 'Signups' },
    'agent.purchases':     { ru: 'Покупки', en: 'Purchases' },

    /* === COMPANY === */
    'company.revenue':      { ru: 'Выручка', en: 'Revenue' },
    'company.products':     { ru: 'Продукты', en: 'Products' },
    'company.monthly_sales':{ ru: 'Продажи за месяц', en: 'Monthly Sales' },
    'company.analytics':    { ru: 'Аналитика', en: 'Analytics' },

    /* === STAFF === */
    'staff.users':         { ru: 'Пользователи', en: 'Users' },
    'staff.kyc_queue':     { ru: 'KYC Очередь', en: 'KYC Queue' },
    'staff.payment_review':{ ru: 'Проверка платежей', en: 'Payment Review' },
    'staff.agent_apps':    { ru: 'Заявки агентов', en: 'Agent Applications' },
    'staff.avatar_mode':   { ru: 'Режим аватара', en: 'Avatar Mode' },
    'staff.pending':       { ru: 'ожидают', en: 'pending' },
    'staff.approve':       { ru: 'Одобрить', en: 'Approve' },
    'staff.reject':        { ru: 'Отклонить', en: 'Reject' },
    'staff.confirm_btn':   { ru: 'Подтвердить', en: 'Confirm' },

    /* === ROLES === */
    'role.investor':       { ru: 'Инвестор', en: 'Investor' },
    'role.investor.desc':  { ru: 'Покупайте продукты, управляйте портфелем и отслеживайте инвестиции', en: 'Buy products, manage your portfolio and track investments' },
    'role.agent':          { ru: 'Агент', en: 'Agent' },
    'role.agent.desc':     { ru: 'Все возможности инвестора плюс реферальная программа и комиссии', en: 'All investor features plus referral program and commissions' },
    'role.company':        { ru: 'Компания', en: 'Company' },
    'role.company.desc':   { ru: 'Размещайте продукты, управляйте продажами и получайте выручку', en: 'List products, manage sales and earn revenue' },

    /* === NAV MAP SECTIONS (auth-flow) === */
    'nav.section.auth':       { ru: 'АУТЕНТИФИКАЦИЯ', en: 'AUTHENTICATION' },
    'nav.section.onboarding': { ru: 'ОНБОРДИНГ', en: 'ONBOARDING' },
    'nav.auth.login':         { ru: 'Вход', en: 'Login' },
    'nav.auth.register':      { ru: 'Регистрация', en: 'Register' },
    'nav.auth.verify':        { ru: 'Проверка Email', en: 'Email Verification' },
    'nav.auth.telegram':      { ru: 'Вход через Telegram', en: 'Telegram Login' },
    'nav.auth.forgot':        { ru: 'Забыли пароль', en: 'Forgot Password' },
    'nav.auth.profile':       { ru: 'Настройка профиля', en: 'Profile Setup' },
    'nav.auth.role':          { ru: 'Выбор роли', en: 'Role Selection' },
    'nav.auth.kyc':           { ru: 'Проверка KYC', en: 'KYC Verification' },
    'nav.auth.sumsub':        { ru: 'SumSub (внешний)', en: 'SumSub (external)' },
    'nav.auth.docs':          { ru: 'Подписание документов', en: 'Document Signing' },
    'nav.auth.complete':      { ru: 'Онбординг завершён', en: 'Onboarding Complete' },

    /* === NAV MAP SECTIONS (investor) === */
    'nav.section.tabs':       { ru: 'ТАБЫ', en: 'TABS' },
    'nav.section.purchase':   { ru: 'ПОКУПКА', en: 'PURCHASE' },
    'nav.section.documents':  { ru: 'ДОКУМЕНТЫ', en: 'DOCUMENTS' },
    'nav.section.endpoints':  { ru: 'КОНЕЧНЫЕ ТОЧКИ', en: 'ENDPOINTS' },
    'nav.inv.dashboard':      { ru: 'Главная', en: 'Dashboard' },
    'nav.inv.portfolio':      { ru: 'Портфель', en: 'Portfolio' },
    'nav.inv.marketplace':    { ru: 'Маркетплейс', en: 'Marketplace' },
    'nav.inv.balance':        { ru: 'Баланс', en: 'Balance' },
    'nav.inv.settings':       { ru: 'Настройки', en: 'Settings' },
    'nav.inv.product':        { ru: 'Детали продукта', en: 'Product Detail' },
    'nav.inv.purchase':       { ru: 'Покупка', en: 'Purchase' },
    'nav.inv.installment':    { ru: 'Рассрочка', en: 'Installment' },
    'nav.inv.documents':      { ru: 'Документы', en: 'Documents' },

    /* === NAV MAP SECTIONS (agent) === */
    'nav.section.agent_hub':  { ru: 'HUB АГЕНТА', en: 'AGENT HUB' },
    'nav.agent.dashboard':    { ru: 'Главная', en: 'Dashboard' },
    'nav.agent.hub':          { ru: 'Hub Агента', en: 'Agent Hub' },
    'nav.agent.commissions':  { ru: 'Комиссии', en: 'Commissions' },
    'nav.agent.passive':      { ru: 'Пассивный баланс', en: 'Passive Balance' },
    'nav.agent.settings':     { ru: 'Настройки', en: 'Settings' },
    'nav.agent.referrals':    { ru: 'Реферальные ссылки', en: 'Referral Links' },
    'nav.agent.leaderboard':  { ru: 'Лидерборд', en: 'Leaderboard' },

    /* === NAV MAP SECTIONS (company) === */
    'nav.comp.dashboard':     { ru: 'Главная', en: 'Dashboard' },
    'nav.comp.products':      { ru: 'Продукты', en: 'Products' },
    'nav.comp.analytics':     { ru: 'Аналитика', en: 'Analytics' },
    'nav.comp.balance':       { ru: 'Баланс', en: 'Balance' },
    'nav.comp.settings':      { ru: 'Настройки', en: 'Settings' },
    'nav.comp.product_edit':  { ru: 'Редактирование продукта', en: 'Product Edit' },

    /* === NAV MAP SECTIONS (staff) === */
    'nav.section.management': { ru: 'УПРАВЛЕНИЕ', en: 'MANAGEMENT' },
    'nav.staff.dashboard':    { ru: 'Главная', en: 'Dashboard' },
    'nav.staff.users':        { ru: 'Пользователи', en: 'Users' },
    'nav.staff.kyc':          { ru: 'KYC Очередь', en: 'KYC Queue' },
    'nav.staff.payments':     { ru: 'Проверка платежей', en: 'Payment Review' },
    'nav.staff.more':         { ru: 'Ещё', en: 'More' },
    'nav.staff.agent_apps':   { ru: 'Заявки агентов', en: 'Agent Applications' },
    'nav.staff.avatar':       { ru: 'Режим аватара', en: 'Avatar Mode' },
  },

  init() {
    const saved = localStorage.getItem(this._key);
    if (saved === 'en' || saved === 'ru') {
      this._locale = saved;
    }
    this.applyI18n();
    this._updateSwitcher();
  },

  t(key, params) {
    const entry = this._dict[key];
    if (!entry) return key;
    let text = entry[this._locale] || entry.ru || key;
    if (params) {
      Object.keys(params).forEach(function(k) {
        text = text.replace('{' + k + '}', params[k]);
      });
    }
    return text;
  },

  setLocale(lang) {
    this._locale = lang;
    localStorage.setItem(this._key, lang);
    this.applyI18n();
    this._updateSwitcher();
    document.documentElement.lang = lang;
    if (typeof showToast === 'function') {
      showToast(lang === 'ru' ? 'Язык: Русский' : 'Language: English');
    }
  },

  toggleLocale() {
    this.setLocale(this._locale === 'ru' ? 'en' : 'ru');
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
