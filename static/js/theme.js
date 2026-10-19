// Применяет палитру (CSS-переменные из /api/state или /api/structure) на лету,
// чтобы смена цветов в админке сразу отражалась на открытых бордах.
(function () {
    let lastTheme = null;

    window.applyTheme = function (vars) {
        if (!vars) return;
        const key = JSON.stringify(vars);
        if (key === lastTheme) return;
        lastTheme = key;

        const root = document.documentElement;
        for (const [name, value] of Object.entries(vars)) {
            root.style.setProperty(name, value);
        }
        root.style.colorScheme = vars['--color-scheme'] || 'dark';

        const meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.content = vars['--bg-page'];
    };
})();
