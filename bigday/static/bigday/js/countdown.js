// Countdown to the date in data-countdown (ISO 8601); data-done is shown once it has passed.
(function () {
    var elements = document.querySelectorAll('[data-countdown]');
    if (!elements.length) {
        return;
    }
    function update() {
        var now = Date.now();
        elements.forEach(function (element) {
            var target = Date.parse(element.dataset.countdown);
            if (isNaN(target)) {
                return;
            }
            var distance = target - now;
            if (distance < 0) {
                element.textContent = element.dataset.done || '';
                return;
            }
            var days = Math.floor(distance / 86400000);
            var hours = Math.floor((distance % 86400000) / 3600000);
            var minutes = Math.floor((distance % 3600000) / 60000);
            var seconds = Math.floor((distance % 60000) / 1000);
            element.textContent = days + ' jours ' + hours + ' heures ' + minutes + ' minutes ' + seconds + ' secondes';
        });
    }
    update();
    setInterval(update, 1000);
})();
