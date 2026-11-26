/* ==========================================================
   section-nav.js — raccourcis de l'en-tête vers les sections de la page
   (tableau de bord du joueur, panneau admin). Styles : .dash-nav dans css/style.css.
   Le lien de la section affichée est mis en valeur pendant le défilement.
   ========================================================== */
'use strict';

// Marge sous l'en-tête collant : un lien vers une section l'amène juste en dessous (pas dessous),
// et une section devient « affichée » quand son haut passe cette limite. Calculée d'après la hauteur réelle
// de l'en-tête, qui change avec la largeur de l'écran (raccourcis sur une deuxième ligne…).
const SECTION_NAV_GAP = 16;
let sectionNavOffset = 96;

function syncSectionNavOffset(header) {
    sectionNavOffset = header.getBoundingClientRect().height + SECTION_NAV_GAP;
    document.documentElement.style.scrollPaddingTop = `${sectionNavOffset}px`;
}

// Section affichée : la dernière (visible) dont le haut est passé sous l'en-tête.
// En haut de la page : la première si activeAtTop, sinon aucune.
// En bas de la page (après avoir défilé) : la dernière, même si son haut n'atteint pas l'en-tête.
function currentSectionId(links, activeAtTop) {
    const ids = [...links].map(link => link.dataset.section)
        .filter(id => document.getElementById(id)?.offsetParent); // sections absentes ou masquées ignorées
    if (window.scrollY <= 0) return activeAtTop ? ids[0] ?? null : null;
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) return ids[ids.length - 1];
    return ids.filter(id => document.getElementById(id).getBoundingClientRect().top <= sectionNavOffset + 1).pop() ?? null;
}

// nav : élément <nav> de l'en-tête qui contient les liens .dash-nav-link (data-section = id de la section)
function watchSections(nav, { activeAtTop = false } = {}) {
    const links = nav.querySelectorAll('.dash-nav-link');
    const header = nav.closest('header');
    let scheduled = false;
    const update = () => {
        scheduled = false;
        syncSectionNavOffset(header);
        const current = currentSectionId(links, activeAtTop);
        links.forEach(link => link.classList.toggle('is-active', link.dataset.section === current));
    };
    window.addEventListener('scroll', () => {
        if (!scheduled) {
            scheduled = true;
            requestAnimationFrame(update);
        }
    }, { passive: true });
    window.addEventListener('resize', update);
    update();
    return update; // à rappeler quand le contenu de la page change (sections chargées)
}
