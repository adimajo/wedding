// Minimal replacement for the Bootstrap navbar toggler (only the Bootstrap CSS is vendored).
document.querySelectorAll('.navbar-toggler').forEach(function (button) {
    button.addEventListener('click', function () {
        var target = document.querySelector(button.dataset.target);
        if (!target) {
            return;
        }
        var open = target.classList.toggle('show');
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
});
// Close the menu after following an in-page link.
document.querySelectorAll('.navbar-collapse .nav-link').forEach(function (link) {
    link.addEventListener('click', function () {
        document.querySelectorAll('.navbar-collapse.show').forEach(function (menu) {
            menu.classList.remove('show');
        });
    });
});
