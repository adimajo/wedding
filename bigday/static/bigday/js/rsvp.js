// Enable the meal choices of a guest only when they are marked as attending.
document.querySelectorAll('.rsvp-guest').forEach(function (block) {
    var radios = block.querySelectorAll('input.attending-radio');
    var meals = block.querySelectorAll('.meal-choices input[type=radio]');
    function refresh() {
        var answer = block.querySelector('input.attending-radio:checked');
        var attending = !answer || answer.value === 'yes';
        meals.forEach(function (meal) {
            meal.disabled = !attending;
            if (!attending) {
                meal.checked = false;
            }
        });
        block.querySelectorAll('.meal-choices').forEach(function (group) {
            group.classList.toggle('text-muted', !attending);
        });
    }
    radios.forEach(function (radio) {
        radio.addEventListener('change', refresh);
    });
    refresh();
});
