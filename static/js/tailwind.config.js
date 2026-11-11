/* Configuration du CDN Tailwind (chargée juste après lui).
   Bordure par défaut : la couleur du thème, pour que les utilitaires `border`,
   `border-b`… sans couleur explicite s'accordent au design (au lieu du gris clair
   par défaut de Tailwind). */
tailwind.config = {
    theme: {
        extend: {
            borderColor: {
                DEFAULT: 'color-mix(in oklab, var(--border) 70%, transparent)'
            }
        }
    }
};
