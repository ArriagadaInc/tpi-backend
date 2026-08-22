(() => {
    'use strict';

    /* ============ 1. HEADER STICKY: sombra al hacer scroll ============ */
    const header = document.getElementById('header');
    const onScroll = () => header.classList.toggle('header--scrolled', window.scrollY > 10);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    /* ============ 2. MENÚ MÓVIL ============ */
    const navToggle = document.getElementById('nav-toggle');
    const nav = document.getElementById('nav');

    navToggle.addEventListener('click', () => {
        const open = nav.classList.toggle('open');
        navToggle.classList.toggle('open', open);
        navToggle.setAttribute('aria-expanded', open);
    });

    nav.querySelectorAll('a').forEach(link =>
        link.addEventListener('click', () => {
            nav.classList.remove('open');
            navToggle.classList.remove('open');
            navToggle.setAttribute('aria-expanded', 'false');
        })
    );

    /* ============ 3. INTERSECTION OBSERVER: animaciones on-scroll ============ */
    const fadeObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('active');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.fade-in-up').forEach(el => fadeObserver.observe(el));

    /* ============ 4. CONTADORES NUMÉRICOS ANIMADOS ============ */
    const animateCounter = (element, target, duration = 2200) => {
        const prefix = element.dataset.prefix || '';
        const suffix = element.dataset.suffix || '';
        let start = null;

        const step = (timestamp) => {
            if (!start) start = timestamp;
            const progress = Math.min((timestamp - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            const value = Math.round(eased * target);
            element.textContent = `${prefix}${value.toLocaleString('es-CL')}${suffix}`;
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    };

    const statsSection = document.getElementById('stats');
    if (statsSection) {
        const statsObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    statsSection.querySelectorAll('.stat__number').forEach(el =>
                        animateCounter(el, parseInt(el.dataset.target, 10))
                    );
                    observer.unobserve(statsSection); // se ejecuta una sola vez
                }
            });
        }, { threshold: 0.35 });
        statsObserver.observe(statsSection);
    }

    /* ============ 5. ACORDEÓN FAQ (permite múltiples abiertas) ============ */
    document.querySelectorAll('.faq__question').forEach(button => {
        button.addEventListener('click', () => {
            const item = button.closest('.faq__item');
            const answer = item.querySelector('.faq__answer');
            const isOpen = item.classList.toggle('open');

            button.setAttribute('aria-expanded', isOpen);
            answer.style.maxHeight = isOpen ? `${answer.scrollHeight}px` : null;
        });
    });

    // Recalcula alturas de respuestas abiertas al redimensionar
    window.addEventListener('resize', () => {
        document.querySelectorAll('.faq__item.open .faq__answer').forEach(answer => {
            answer.style.maxHeight = `${answer.scrollHeight}px`;
        });
    });
})();