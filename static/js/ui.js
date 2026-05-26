// Minimal UI helpers for the server-rendered frontend
document.addEventListener('DOMContentLoaded', function () {
  // Flashcards (weighted selection)
  let rawCards = window.reviewCards || [];
  // If server embedded JSON as a string, try to parse it
  if (typeof rawCards === 'string') {
    try {
      rawCards = JSON.parse(rawCards);
    } catch (e) {
      console.warn('reviewCards JSON parse failed', e);
      rawCards = [];
    }
  }
  const cards = Array.isArray(rawCards) ? rawCards : [];
  let currentCard = null;
  let currentIndex = -1;
  let deck = [];
  let deckPos = -1;
  let flipped = false;
  const reviewedSet = new Set();

  function totalWeight() {
    try {
      return cards.reduce((s, c) => s + (c.weight || 1), 0);
    } catch (e) {
      console.warn('totalWeight error', e);
      return cards.length || 0;
    }
  }

  function shuffle(array) {
    for (let i = array.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
  }

  function buildDeck() {
    const built = [];
    cards.forEach((c, idx) => {
      const w = Math.max(1, Math.min(10, Number(c.weight) || 1));
      for (let i = 0; i < w; i++) built.push(idx);
    });
    deck = shuffle(built);
    deckPos = -1;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderExamples(lines) {
    const list = document.getElementById('card-examples');
    if (!list) return;
    const items = Array.isArray(lines) ? lines.slice(0, 2) : [];
    const structured = currentCard && Array.isArray(currentCard.example_structures) ? currentCard.example_structures : [];

    if (structured.length) {
      list.innerHTML = structured.map((item) => {
        if (item.german) {
          return `
            <li class="noun-example-line rounded-md bg-white/70 px-3 py-2 border border-green-100">
              <div>${escapeHtml(item.german || '')}</div>
              <div class="example-translation">${escapeHtml(item.translation || '')}</div>
            </li>
          `;
        }
        const article = item.article || '';
        const prefix = article ? escapeHtml(article.charAt(0)) : '';
        const rest = article.length > 1 ? escapeHtml(article.slice(1)) : '';
        return `
          <li class="noun-example-line rounded-md bg-white/70 px-3 py-2 border border-green-100">
            <div>
              <span class="example-muted">${escapeHtml(item.before || '')}</span><span class="article-prefix">${prefix}</span><span class="article-colored ${articleClass(currentCard)}">${rest}</span>${article ? ' ' : ''}<span class="article-colored ${articleClass(currentCard)}">${escapeHtml(item.colored || '')}</span><span class="example-muted">${escapeHtml(item.after || '')}</span>
            </div>
            <div class="example-translation">${escapeHtml(item.translation || '')}</div>
          </li>
        `;
      }).join('');
      return;
    }

    list.innerHTML = items.map((line) => `<li class="rounded-md bg-white/70 px-3 py-2 border border-green-100">${escapeHtml(line)}</li>`).join('');
  }

  function setActiveReviewTab(name) {
    const tabs = Array.from(document.querySelectorAll('[data-review-tab]'));
    const panels = {
      examples: document.getElementById('panel-examples'),
      grammar: document.getElementById('panel-grammar'),
      verbs: document.getElementById('panel-verbs'),
    };
    tabs.forEach((tab) => {
      const active = tab.dataset.reviewTab === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    Object.entries(panels).forEach(([key, panel]) => {
      if (panel) panel.classList.toggle('hidden', key !== name);
    });
  }

  function defaultReviewTab(card) {
    if (card && card.is_verb && card.verb_forms_data && card.verb_forms_data.meta) return 'verbs';
    if (card && card.grammar_hint) return 'grammar';
    return 'examples';
  }

  function renderAnswerStrip(card) {
    const strip = document.getElementById('review-answer-strip');
    const translation = document.getElementById('answer-translation');
    const meta = document.getElementById('answer-meta');
    const chips = document.getElementById('answer-verb-chips');
    if (!strip || !translation || !meta || !chips || !card) return;

    strip.classList.remove('hidden');
    translation.textContent = card.back || '';
    const metaParts = [];
    if (card.part_of_speech_label) metaParts.push(card.part_of_speech_label);
    if (card.category) metaParts.push(card.category);
    if (card.level) metaParts.push(card.level);
    meta.innerHTML = metaParts.map((item) => `<span>${escapeHtml(item)}</span>`).join('');

    const rows = card.verb_forms_data && Array.isArray(card.verb_forms_data.present_rows)
      ? card.verb_forms_data.present_rows
      : [];
    const quickRows = rows.filter((row) => ['ich', 'du', 'er/sie/es'].includes(row.pronoun));
    if (card.is_verb && quickRows.length) {
      chips.classList.remove('hidden');
      chips.innerHTML = quickRows.map((row) => `<span>${escapeHtml(row.pronoun)} <strong>${escapeHtml(row.form)}</strong></span>`).join('');
    } else {
      chips.classList.add('hidden');
      chips.innerHTML = '';
    }
  }

  function renderGrammarHint(hint) {
    const section = document.getElementById('grammar-hint-section');
    const title = document.getElementById('grammar-hint-title');
    const bullets = document.getElementById('grammar-hint-bullets');
    const pattern = document.getElementById('grammar-hint-pattern');
    const example = document.getElementById('grammar-hint-example');
    const link = document.getElementById('grammar-hint-link');
    if (!section || !title || !bullets || !pattern || !example || !link) return;

    if (!hint) {
      section.style.display = 'none';
      return;
    }

    section.style.display = '';
    title.textContent = hint.title || 'Grammar Hint';
    bullets.innerHTML = (hint.bullets || [])
      .map((item) => `<li class="rounded-md bg-white/70 px-3 py-2 border border-blue-100">${escapeHtml(item)}</li>`)
      .join('');
    pattern.innerHTML = hint.pattern ? `<span class="font-semibold">Pattern:</span> ${escapeHtml(hint.pattern)}` : '';
    example.innerHTML = hint.example ? `<span class="font-semibold">Example:</span> ${escapeHtml(hint.example)}` : '';
    link.textContent = hint.topic_label || 'Practice Grammar';
    if (hint.topic_slug === 'adjective-endings') {
      link.href = '/grammar/personal/adjective-endings/';
    } else {
      link.href = hint.topic_slug ? `/grammar/${encodeURIComponent(hint.topic_slug)}/` : '/grammar/';
    }
  }

  function articleClass(card) {
    const key = card && card.article_color_key ? card.article_color_key : '';
    return key ? `article-${key}` : '';
  }

  function renderLanguageMeta(card) {
    const meta = document.getElementById('card-language-meta');
    const badge = document.getElementById('card-meta-badge');
    const pluralBadge = document.getElementById('card-plural-badge');
    const front = document.getElementById('card-front');
    if (!card) return;

    if (badge) badge.textContent = card.part_of_speech_label || '';
    if (pluralBadge) {
      const isPlural = card.part_of_speech === 'noun' && (card.gender === 'plural' || card.article === 'plural');
      pluralBadge.classList.toggle('hidden', !isPlural);
      pluralBadge.classList.toggle('article-plural-badge', isPlural);
    }
    if (front) {
      front.classList.remove('article-der', 'article-die', 'article-das', 'article-plural');
      const cls = articleClass(card);
      if (cls) front.classList.add(cls);
    }

    if (!meta) return;
    const parts = [];
    if (card.part_of_speech_label) parts.push(`<span><strong>Type:</strong> ${escapeHtml(card.part_of_speech_label)}</span>`);
    if (card.part_of_speech === 'noun' && (card.article || card.gender)) {
      const article = card.gender === 'plural' ? 'die (plural)' : card.article;
      parts.push(`<span><strong>Article:</strong> ${escapeHtml(article || '')}</span>`);
      parts.push(`<span><strong>Gender:</strong> ${escapeHtml(card.gender || '')}</span>`);
      if (card.plural_form) parts.push(`<span><strong>Plural:</strong> ${escapeHtml(card.plural_form)}</span>`);
    }
    if (card.category) parts.push(`<span><strong>Category:</strong> ${escapeHtml(card.category)}</span>`);

    if (!parts.length) {
      meta.classList.add('hidden');
      meta.innerHTML = '';
      return;
    }

    meta.classList.remove('hidden');
    meta.innerHTML = `<div class="flex flex-wrap gap-3">${parts.join('')}</div>`;
  }

  function renderCardFront(card) {
    if (!card) return '';
    if (card.part_of_speech !== 'noun' || !card.nominative_article || !card.noun_text) {
      return escapeHtml(card.front || '');
    }
    const article = card.nominative_article;
    const prefix = escapeHtml(article.charAt(0));
    const rest = escapeHtml(article.slice(1));
    const noun = escapeHtml(card.noun_text);
    const colorClass = articleClass(card);
    return `<span class="article-display"><span class="article-token"><span class="article-prefix">${prefix}</span><span class="article-colored ${colorClass}">${rest}</span></span><span class="article-colored ${colorClass}">${noun}</span></span>`;
  }

  function fitFlashcardText(el) {
    if (!el) return;
    const baseSize = 48;
    const minSize = 24;
    el.style.fontSize = `${baseSize}px`;

    while (
      parseFloat(el.style.fontSize) > minSize &&
      (el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight)
    ) {
      el.style.fontSize = `${parseFloat(el.style.fontSize) - 2}px`;
    }
  }

  function fitCurrentFlashcardText() {
    fitFlashcardText(document.getElementById('card-front'));
    fitFlashcardText(document.getElementById('card-back'));
  }

  function renderVerbForms(data) {
    const verbSection = document.getElementById('verb-section');
    const verbTab = document.getElementById('tab-verbs');
    const summaryBody = document.getElementById('verb-summary-body');
    const presentBody = document.getElementById('verb-present-body');
    const perfectBody = document.getElementById('verb-perfect-body');
    const pastBody = document.getElementById('verb-past-body');
    const compactPresent = document.getElementById('verb-compact-present');
    const compactMeta = document.getElementById('verb-compact-meta');
    window.__verbRenderState = {
      isVerb: !!currentCard.is_verb,
      hasData: !!currentCard.verb_forms_data,
      hasMeta: !!(currentCard.verb_forms_data && currentCard.verb_forms_data.meta),
      hasBodies: !!(summaryBody && presentBody && perfectBody && pastBody),
      front: currentCard.front,
    };

    if (!verbSection || !summaryBody || !presentBody || !pastBody || !perfectBody || !compactPresent || !compactMeta || !verbTab) return;

    if (!data || !data.meta) {
      verbSection.classList.add('hidden');
      verbTab.classList.add('hidden');
      summaryBody.innerHTML = '';
      presentBody.innerHTML = '';
      pastBody.innerHTML = '';
      perfectBody.innerHTML = '';
      compactPresent.innerHTML = '';
      compactMeta.innerHTML = '';
      return;
    }

    verbSection.classList.remove('hidden');
    verbTab.classList.remove('hidden');
    const meta = data.meta || {};
    summaryBody.innerHTML = `
      <tr class="border-b border-purple-100"><th class="px-3 py-2 text-left bg-white/70">Verb</th><td class="px-3 py-2 bg-white">${escapeHtml(meta.verb || '')}</td></tr>
      <tr class="border-b border-purple-100"><th class="px-3 py-2 text-left bg-white/70">Meaning</th><td class="px-3 py-2 bg-white">${escapeHtml(meta.meaning || '')}</td></tr>
      <tr><th class="px-3 py-2 text-left bg-white/70">Type</th><td class="px-3 py-2 bg-white">${escapeHtml(meta.type || '')}</td></tr>
    `;

    const renderRows = (rows) => rows.map((row) => `<tr class="border-b border-purple-100 last:border-b-0"><td class="px-3 py-2 font-medium">${escapeHtml(row.pronoun || '')}</td><td class="px-3 py-2">${escapeHtml(row.form || '')}</td></tr>`).join('');
    presentBody.innerHTML = renderRows(data.present_rows || []);
    perfectBody.innerHTML = `
      <tr class="border-b border-purple-100"><td class="px-3 py-2 font-medium">Participle</td><td class="px-3 py-2">${escapeHtml(meta.participle || '')}</td></tr>
      <tr><td class="px-3 py-2 font-medium">Auxiliary</td><td class="px-3 py-2">${escapeHtml(meta.auxiliary || '')}</td></tr>
    `;
    pastBody.innerHTML = renderRows(data.past_rows || []);

    const presentRows = data.present_rows || [];
    compactPresent.innerHTML = presentRows.map((row) => `
      <div class="verb-compact-cell">
        <span>${escapeHtml(row.pronoun || '')}</span>
        <strong>${escapeHtml(row.form || '')}</strong>
      </div>
    `).join('');
    const pastFirst = (data.past_rows || []).find((row) => row.pronoun === 'ich') || (data.past_rows || [])[0] || {};
    compactMeta.innerHTML = `
      <div><span>Verb</span><strong>${escapeHtml(meta.verb || '')}</strong></div>
      <div><span>Meaning</span><strong>${escapeHtml(meta.meaning || '')}</strong></div>
      <div><span>Past</span><strong>${escapeHtml(pastFirst.form || '-')}</strong></div>
      <div><span>Perfect</span><strong>${escapeHtml(meta.auxiliary || '-')} ${escapeHtml(meta.participle || '')}</strong></div>
    `;
  }

  function showCardByIndex(i, pushHistory = true) {
    if (!cards.length) return;
    currentIndex = ((i % cards.length) + cards.length) % cards.length;
    currentCard = cards[currentIndex];
    flipped = false;
    const frontEl = document.getElementById('card-front');
    const backEl = document.getElementById('card-back');
    const idxEl = document.getElementById('card-index');
    const pctEl = document.getElementById('card-percent');
    const verbSection = document.getElementById('verb-section');
    const summaryBody = document.getElementById('verb-summary-body');
    const presentBody = document.getElementById('verb-present-body');
    const perfectBody = document.getElementById('verb-perfect-body');
    const pastBody = document.getElementById('verb-past-body');
    frontEl.innerHTML = renderCardFront(currentCard);
    backEl.textContent = currentCard.back;
    renderLanguageMeta(currentCard);
    renderAnswerStrip(currentCard);
    fitCurrentFlashcardText();
    renderExamples(currentCard.examples || []);
    renderGrammarHint(currentCard.grammar_hint);
    renderVerbForms(currentCard.is_verb ? currentCard.verb_forms_data : null);
    setActiveReviewTab(defaultReviewTab(currentCard));
    if (currentCard && currentCard.pk) reviewedSet.add(currentCard.pk);
    const reviewedCount = Math.min(reviewedSet.size, cards.length);
    idxEl.textContent = `${reviewedCount} / ${cards.length}`;
    const reviewedPct = Math.min(100, Math.round((reviewedCount / cards.length) * 100));
    if (pctEl) pctEl.textContent = `${reviewedPct}% Complete`;
    document.getElementById('progress-bar').style.width = `${reviewedPct}%`;
    const reviewedInput = document.getElementById('reviewed-pks-input');
    if (reviewedInput) reviewedInput.value = Array.from(reviewedSet).join(',');
    // reset flip state visually
    const container = document.getElementById('card-container');
    const inner = document.getElementById('card-inner');
    if (container) container.classList.remove('is-flipped');
    if (inner) inner.style.transform = 'rotateY(0deg)';
    const levelBadge = document.getElementById('card-level-badge');
    if (levelBadge) levelBadge.textContent = currentCard.level || '';
  }

  function showPreviousCard() {
    if (!cards.length) return;
    showCardByIndex(currentIndex <= 0 ? cards.length - 1 : currentIndex - 1, false);
  }

  function pickAndShow() {
    if (!cards.length) return;
    showCardByIndex(currentIndex + 1);
  }

  function flipCard() {
    if (!currentCard) return;
    flipped = !flipped;
    const container = document.getElementById('card-container');
    const inner = document.getElementById('card-inner');
    if (!container || !inner) return;
    // toggle class for CSS animation
    container.classList.toggle('is-flipped', flipped);
    // also set transform directly for robustness
    if (flipped) {
      inner.style.transform = 'rotateY(180deg)';
    } else {
      inner.style.transform = 'rotateY(0deg)';
    }
  }

  document.getElementById('card-next')?.addEventListener('click', function () { flipCardIfNeeded(false); pickAndShow(); });
  document.getElementById('card-prev')?.addEventListener('click', function () { flipCardIfNeeded(false); showPreviousCard(); });
  document.getElementById('card-flip-zone')?.addEventListener('click', flipCard);
  document.querySelectorAll('[data-review-tab]').forEach((tab) => {
    tab.addEventListener('click', () => setActiveReviewTab(tab.dataset.reviewTab));
  });
  window.addEventListener('resize', fitCurrentFlashcardText);

  function flipCardIfNeeded(flag) {
    flipped = flag;
    const container = document.getElementById('card-container');
    const inner = document.getElementById('card-inner');
    if (container) container.classList.remove('is-flipped');
    if (inner) inner.style.transform = 'rotateY(0deg)';
  }

  // Play / Pause autoplay
  // autoplay removed

  // Initial render if cards exist
  try {
    if (cards.length) {
      buildDeck();
      pickAndShow();
    }
  } catch (err) {
    console.error('Flashcards initialization error:', err);
  }

  // Simple search focus for vocabulary page
  const searchInput = document.querySelector('input[name="search"]');
  if (searchInput) {
    const focusBtn = document.getElementById('focus-search');
    if (focusBtn) focusBtn.addEventListener('click', () => searchInput.focus());
  }

  // Quiz form enable/selection handling
  const quizForm = document.getElementById('quiz-form');
  if (quizForm) {
    const submitBtn = document.getElementById('quiz-submit');
    const radios = Array.from(quizForm.querySelectorAll('.option-radio'));
    const labels = Array.from(quizForm.querySelectorAll('.option-label'));

    radios.forEach((r, idx) => {
      r.addEventListener('change', () => {
        if (submitBtn) submitBtn.disabled = false;
        labels.forEach((lab, i) => {
          lab.classList.toggle('ring-ring', i === idx);
        });
      });
    });
  }
});

/* Small CSS helper appended via JS is avoided; styles live in theme.css */
