/** Landing interactions (cursor, scroll reveals) — from NAMOS theme, adapted for NextStep. */
const cursor = document.getElementById('cursor');
const ring = document.getElementById('cursorRing');

if (cursor && ring && window.matchMedia('(hover: hover)').matches) {
  let mx = 0;
  let my = 0;
  let rx = 0;
  let ry = 0;
  document.addEventListener('mousemove', (e) => {
    mx = e.clientX;
    my = e.clientY;
    cursor.style.left = `${mx}px`;
    cursor.style.top = `${my}px`;
  });
  (function animRing() {
    rx += (mx - rx) * 0.1;
    ry += (my - ry) * 0.1;
    ring.style.left = `${rx}px`;
    ring.style.top = `${ry}px`;
    requestAnimationFrame(animRing);
  })();
  document.querySelectorAll('a, button, input, summary').forEach((el) => {
    el.addEventListener('mouseenter', () => {
      cursor.style.width = '14px';
      cursor.style.height = '14px';
      ring.style.width = '48px';
      ring.style.height = '48px';
      ring.style.borderColor = 'var(--accent)';
    });
    el.addEventListener('mouseleave', () => {
      cursor.style.width = '8px';
      cursor.style.height = '8px';
      ring.style.width = '32px';
      ring.style.height = '32px';
      ring.style.borderColor = 'var(--accent-dim)';
    });
  });
}

const obs = new IntersectionObserver(
  (entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        e.target.style.transitionDelay = e.target.dataset.delay || '0s';
      }
    });
  },
  { threshold: 0.12 }
);
document.querySelectorAll('.fade-in').forEach((el, i) => {
  el.dataset.delay = `${(i % 4) * 0.1}s`;
  obs.observe(el);
});

const meter = document.getElementById('meterFill');
if (meter) {
  const meterObs = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          meter.style.width = '0%';
          setTimeout(() => {
            meter.style.width = '72%';
          }, 200);
        }
      });
    },
    { threshold: 0.3 }
  );
  meterObs.observe(meter);
}

document.querySelectorAll('a[href^="#"]').forEach((a) => {
  a.addEventListener('click', (e) => {
    const t = document.querySelector(a.getAttribute('href'));
    if (t) {
      e.preventDefault();
      t.scrollIntoView({ behavior: 'smooth' });
    }
  });
});
