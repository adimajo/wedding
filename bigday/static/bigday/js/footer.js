// Keep the footer at the bottom of the viewport on short pages.
function setFooterStyle() {
    var footer = document.getElementById('footer');
    if (!footer) {
        return;
    }
    footer.style.marginTop = '';
    var footerBottom = footer.getBoundingClientRect().bottom + window.scrollY;
    if (footerBottom < window.innerHeight) {
        footer.style.marginTop = (window.innerHeight - footerBottom) + 'px';
    }
    footer.classList.remove('invisible');
}
window.addEventListener('load', setFooterStyle);
window.addEventListener('resize', setFooterStyle);
