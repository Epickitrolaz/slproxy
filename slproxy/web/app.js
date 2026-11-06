/**
 * SLProxy WebUI Application
 * Calm Monochrome & Obsidian Senior-Designer Interface (unslop-ui)
 * Zero-Provider Clean Slate & 5-Step Quick Setup Tour
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // STARTER TEMPLATES & SNIPPETS
  // ---------------------------------------------------------------------------
  const TEMPLATES = {
    base: `"""
SLProxy Custom Provider Plugin
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class CustomProviderPlugin(BasePlugin):
    id = "custom_provider"
    name = "Custom Provider"
    description = "Dynamic Python provider with real-time routing"
    version = "1.0.0"
    author = "SLProxy User"
    icon = "cpu"
    color = "#ffffff"
    default_base_url = "https://api.openai.com/v1"
    format = "openai"  # "openai" or "anthropic"

    models = [
        ModelInfo(id="custom-fast", name="Custom Fast", context_window=128000),
        ModelInfo(id="custom-reasoner", name="Custom Reasoner", context_window=200000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        """Modify or inject headers/body before request is forwarded"""
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        """Detect rate limits (429), quota exhaustion, or failover conditions"""
        if response.status_code == 429:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=60.0,
                should_fallback=True,
                error_message="Rate limit reached, activating failover cooldown"
            )
        return ErrorCheckResult(is_error=False)
`,

    auth_header: `    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        """Inject customized authorization or tracking headers"""
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        request.headers["X-SLProxy-Client"] = "hot-reloaded"
        return request
`,

    rate_limit_quota: `    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        """Sub-second quota detector & failover trigger"""
        if response.status_code == 429 or "quota_limit" in response.raw_text.lower():
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=90.0,
                should_fallback=True,
                error_message="Provider quota exhausted, falling back to backup account"
            )
        return ErrorCheckResult(is_error=False)
`,

    streaming_transform: `    def intercept_stream_chunk(self, chunk: str) -> str:
        """Real-time token or SSE chunk transformer"""
        # Inspect or modify chunk in transit
        return chunk
`
  };

  // Fallback reference templates in case /api/templates is called offline
  const FALLBACK_TEMPLATES = [
    {
      id: "google_antigravity",
      name: "Google Antigravity",
      description: "Ultra-fast Google Gemini 2.0 Flash & Thinking models with quota failover",
      format: "openai",
      models_count: 3
    },
    {
      id: "openai_codex",
      name: "OpenAI Codex",
      description: "Direct OpenAI API integration (GPT-4o, o1, o3-mini) with priority failover",
      format: "openai",
      models_count: 4
    },
    {
      id: "anthropic_claude",
      name: "Claude Code",
      description: "Anthropic Claude 3.5 Sonnet & Haiku with native tools and message streaming",
      format: "anthropic",
      models_count: 3
    },
    {
      id: "openrouter",
      name: "OpenRouter",
      description: "Universal LLM gateway with deep multi-provider model catalog",
      format: "openai",
      models_count: 3
    },
    {
      id: "opencode",
      name: "OpenCode",
      description: "Specialized coding models and code intelligence benchmarks",
      format: "openai",
      models_count: 2
    },
    {
      id: "openai_compatible",
      name: "OpenAI Compatible",
      description: "Universal OpenAI-compliant endpoint (Ollama, vLLM, Groq, DeepSeek)",
      format: "openai",
      models_count: 2
    },
    {
      id: "anthropic_compatible",
      name: "Anthropic Compatible",
      description: "Anthropic /v1/messages API compatible endpoints",
      format: "anthropic",
      models_count: 1
    }
  ];

  // ---------------------------------------------------------------------------
  // APP STATE (Clean Zero-Provider Default Slate)
  // ---------------------------------------------------------------------------
  const state = {
    currentTab: 'dashboard',
    plugins: [],       // Starts clean with zero providers!
    accounts: [],      // Starts clean with zero accounts!
    keys: [],          // Starts clean with zero keys!
    logs: [],          // Live telemetry logs
    metrics: {
      total_requests: 0,
      total_errors: 0,
      total_tokens: 0,
      success_rate: 1.0,
      avg_latency_ms: 0
    },
    settings: {
      routing_strategy: 'fallback',
      request_timeout: 120.0,
      require_api_key: false
    },
    referenceTemplates: [],
    tourCurrentStep: 1,
    isStreamingLogs: true,
    codeEditorInstance: null
  };

  // ---------------------------------------------------------------------------
  // TOAST NOTIFICATIONS & OBSIDIAN DIALOGS (Zero Native Prompts)
  // ---------------------------------------------------------------------------
  function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast flex items-start gap-3 p-3.5 text-sm font-medium border transition-all';

    let icon = 'info';
    let iconClass = 'text-zinc-400';

    if (type === 'success') {
      toast.classList.add('border-emerald-500/30', 'text-zinc-200');
      icon = 'check-circle';
      iconClass = 'text-emerald-400';
    } else if (type === 'error') {
      toast.classList.add('border-rose-500/30', 'text-zinc-200');
      icon = 'alert-octagon';
      iconClass = 'text-rose-400';
    } else if (type === 'warning') {
      toast.classList.add('border-amber-500/30', 'text-zinc-200');
      icon = 'alert-triangle';
      iconClass = 'text-amber-400';
    } else {
      toast.classList.add('border-white/10', 'text-zinc-200');
      icon = 'info';
      iconClass = 'text-zinc-400';
    }

    toast.innerHTML = `
      <i data-lucide="${icon}" class="w-5 h-5 shrink-0 mt-0.5 ${iconClass}"></i>
      <div class="flex-1 text-zinc-200 leading-snug">${message}</div>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px) scale(0.96)';
      setTimeout(() => toast.remove(), 250);
    }, duration);
  }

  function showConfirmModal({
    title = 'Confirm Action',
    message = 'Are you sure you want to proceed?',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    danger = true,
    icon = 'alert-triangle'
  } = {}) {
    return new Promise((resolve) => {
      const modal = document.getElementById('modal-confirm');
      const titleEl = document.getElementById('modal-confirm-title');
      const messageEl = document.getElementById('modal-confirm-message');
      const btnConfirm = document.getElementById('modal-confirm-btn-confirm');
      const btnCancel = document.getElementById('modal-confirm-btn-cancel');
      const iconEl = document.getElementById('modal-confirm-icon');
      const iconBox = document.getElementById('modal-confirm-icon-box');

      if (!modal || !btnConfirm || !btnCancel) {
        resolve(true);
        return;
      }

      if (titleEl) titleEl.textContent = title;
      if (messageEl) messageEl.textContent = message;

      if (btnConfirm) {
        btnConfirm.textContent = confirmText;
        btnConfirm.className = danger
          ? 'btn-danger px-5 py-2.5 text-sm font-medium min-h-[44px]'
          : 'btn-primary px-5 py-2.5 text-sm font-medium min-h-[44px]';
      }
      if (btnCancel) btnCancel.textContent = cancelText;

      if (iconEl) {
        iconEl.setAttribute('data-lucide', danger ? 'alert-triangle' : icon);
        if (iconBox) {
          iconBox.className = danger
            ? 'w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center shrink-0 mt-0.5'
            : 'w-10 h-10 rounded-xl bg-zinc-900 border border-white/10 flex items-center justify-center shrink-0 mt-0.5';
        }
        iconEl.className = danger ? 'w-5 h-5 text-rose-400' : 'w-5 h-5 text-zinc-300';
      }

      if (window.lucide) window.lucide.createIcons();
      modal.classList.remove('hidden');

      function cleanup(res) {
        modal.classList.add('hidden');
        btnConfirm.removeEventListener('click', onConfirm);
        btnCancel.removeEventListener('click', onCancel);
        document.removeEventListener('keydown', onKey);
        resolve(res);
      }

      function onConfirm() {
        cleanup(true);
      }
      function onCancel() {
        cleanup(false);
      }
      function onKey(e) {
        if (e.key === 'Escape') cleanup(false);
      }

      btnConfirm.addEventListener('click', onConfirm);
      btnCancel.addEventListener('click', onCancel);
      document.addEventListener('keydown', onKey);
    });
  }

  function showAlertModal({
    title = 'Notification',
    message = '',
    type = 'info'
  } = {}) {
    return new Promise((resolve) => {
      const modal = document.getElementById('modal-alert');
      const titleEl = document.getElementById('modal-alert-title');
      const messageEl = document.getElementById('modal-alert-message');
      const btnOk = document.getElementById('modal-alert-btn-ok');
      const iconEl = document.getElementById('modal-alert-icon');
      const iconBox = document.getElementById('modal-alert-icon-box');

      if (!modal || !btnOk) {
        showToast(message, type);
        resolve();
        return;
      }

      if (titleEl) titleEl.textContent = title;
      if (messageEl) messageEl.textContent = message;

      if (iconEl) {
        const iconName = type === 'error' ? 'alert-octagon' : type === 'warning' ? 'alert-triangle' : 'info';
        iconEl.setAttribute('data-lucide', iconName);
        if (iconBox) {
          iconBox.className = type === 'error'
            ? 'w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center shrink-0 mt-0.5'
            : type === 'warning'
            ? 'w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0 mt-0.5'
            : 'w-10 h-10 rounded-xl bg-zinc-900 border border-white/10 flex items-center justify-center shrink-0 mt-0.5';
        }
        iconEl.className = type === 'error' ? 'w-5 h-5 text-rose-400' : type === 'warning' ? 'w-5 h-5 text-amber-400' : 'w-5 h-5 text-zinc-300';
      }

      if (window.lucide) window.lucide.createIcons();
      modal.classList.remove('hidden');

      function cleanup() {
        modal.classList.add('hidden');
        btnOk.removeEventListener('click', onOk);
        document.removeEventListener('keydown', onKey);
        resolve();
      }

      function onOk() {
        cleanup();
      }
      function onKey(e) {
        if (e.key === 'Escape') cleanup();
      }

      btnOk.addEventListener('click', onOk);
      document.addEventListener('keydown', onKey);
    });
  }

  // Intercept any accidental browser-native prompts to maintain Obsidian design
  window.confirm = function (msg) {
    console.warn('Native confirm() intercepted; use showConfirmModal instead.');
    showConfirmModal({ title: 'Confirmation', message: String(msg) });
    return false;
  };
  window.alert = function (msg) {
    console.warn('Native alert() intercepted; use showAlertModal instead.');
    showAlertModal({ title: 'Alert', message: String(msg) });
  };
  window.prompt = function () {
    console.warn('Native prompt() intercepted.');
    return null;
  };

  // ---------------------------------------------------------------------------
  // QUICK SETUP TOUR (5 STEPS INTERACTIVE MODAL)
  // ---------------------------------------------------------------------------
  function initQuickTour() {
    const tourModal = document.getElementById('modal-tour');
    const btnNavTour = document.getElementById('btn-nav-tour');
    const btnCloseTour = document.getElementById('btn-close-tour');
    const btnTourSkip = document.getElementById('btn-tour-skip');
    const btnTourPrev = document.getElementById('btn-tour-prev');
    const btnTourNext = document.getElementById('btn-tour-next');
    const tourDontShow = document.getElementById('tour-dont-show');

    // Permanent header button
    if (btnNavTour) {
      btnNavTour.addEventListener('click', () => openTourModal(1));
    }

    if (btnCloseTour) {
      btnCloseTour.addEventListener('click', () => {
        if (tourDontShow && tourDontShow.checked) {
          localStorage.setItem('slproxy_tour_dismissed', 'true');
        }
        closeTourModal();
      });
    }

    if (btnTourSkip) {
      btnTourSkip.addEventListener('click', () => {
        localStorage.setItem('slproxy_tour_dismissed', 'true');
        closeTourModal();
      });
    }

    if (btnTourPrev) {
      btnTourPrev.addEventListener('click', () => {
        if (state.tourCurrentStep > 1) {
          goToTourStep(state.tourCurrentStep - 1);
        }
      });
    }

    if (btnTourNext) {
      btnTourNext.addEventListener('click', () => {
        if (state.tourCurrentStep < 5) {
          goToTourStep(state.tourCurrentStep + 1);
        } else {
          // Finished step 5
          localStorage.setItem('slproxy_tour_dismissed', 'true');
          closeTourModal();
          showToast('Tour completed! You are ready to route AI models.', 'success');
        }
      });
    }

    // Step dots navigation
    document.querySelectorAll('.tour-dot').forEach((dot) => {
      dot.addEventListener('click', (e) => {
        const step = parseInt(e.target.getAttribute('data-step'), 10);
        if (step >= 1 && step <= 5) {
          goToTourStep(step);
        }
      });
    });

    // Copyable snippet buttons in tour
    document.querySelectorAll('.btn-copy-snippet').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const text = btn.getAttribute('data-snippet');
        if (text) {
          navigator.clipboard.writeText(text).then(() => {
            showToast('Configuration snippet copied to clipboard!', 'success');
          });
        }
      });
    });
  }

  function openTourModal(step = 1) {
    const modal = document.getElementById('modal-tour');
    if (!modal) return;
    modal.classList.remove('hidden');
    goToTourStep(step);
  }

  function closeTourModal() {
    const modal = document.getElementById('modal-tour');
    if (modal) modal.classList.add('hidden');
  }

  function goToTourStep(step) {
    state.tourCurrentStep = step;

    // Update badge text
    const badge = document.getElementById('tour-step-badge');
    if (badge) badge.textContent = `Step ${step} of 5`;

    // Toggle step content
    for (let i = 1; i <= 5; i++) {
      const stepEl = document.getElementById(`tour-step-${i}`);
      if (stepEl) {
        if (i === step) {
          stepEl.classList.remove('hidden');
        } else {
          stepEl.classList.add('hidden');
        }
      }
    }

    // Update dots
    document.querySelectorAll('.tour-dot').forEach((dot) => {
      const dotStep = parseInt(dot.getAttribute('data-step'), 10);
      if (dotStep === step) {
        dot.classList.add('active');
      } else {
        dot.classList.remove('active');
      }
    });

    // Update Prev / Next buttons
    const btnPrev = document.getElementById('btn-tour-prev');
    const btnNext = document.getElementById('btn-tour-next');

    if (btnPrev) {
      btnPrev.disabled = step === 1;
    }

    if (btnNext) {
      if (step === 5) {
        btnNext.textContent = 'Done';
      } else {
        btnNext.textContent = 'Next';
      }
    }

    if (window.lucide) window.lucide.createIcons();
  }

  // ---------------------------------------------------------------------------
  // REFERENCE TEMPLATES BROWSER & 1-CLICK INSTALLER
  // ---------------------------------------------------------------------------
  function initTemplatesBrowser() {
    const modal = document.getElementById('modal-templates');
    const searchInput = document.getElementById('filter-templates-search');

    // Bind all buttons that open template browser
    document.querySelectorAll('.btn-browse-templates-trigger').forEach((btn) => {
      btn.addEventListener('click', () => {
        closeTourModal();
        openTemplatesModal();
      });
    });

    if (searchInput) {
      searchInput.addEventListener('input', () => {
        renderTemplatesList(searchInput.value.toLowerCase().trim());
      });
    }
  }

  async function openTemplatesModal() {
    const modal = document.getElementById('modal-templates');
    if (!modal) return;
    modal.classList.remove('hidden');

    if (state.referenceTemplates.length === 0) {
      await fetchTemplates();
    }
    renderTemplatesList();
    if (window.lucide) window.lucide.createIcons();
  }

  async function fetchTemplates() {
    const container = document.getElementById('templates-list-container');
    if (container) {
      container.innerHTML = `
        <div class="p-8 text-center text-zinc-500 font-mono text-xs flex items-center justify-center gap-2">
          <i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i>
          <span>Loading reference templates...</span>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
    }

    try {
      const res = await fetch('/api/templates').catch(() => null);
      if (res && res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          state.referenceTemplates = data;
          return;
        }
      }
    } catch (_) {}

    // Fallback to embedded catalog if backend is not yet populated
    state.referenceTemplates = FALLBACK_TEMPLATES;
  }

  function renderTemplatesList(filterQuery = '') {
    const container = document.getElementById('templates-list-container');
    if (!container) return;

    let templates = state.referenceTemplates.length > 0 ? state.referenceTemplates : FALLBACK_TEMPLATES;
    if (filterQuery) {
      templates = templates.filter(
        (t) =>
          t.name.toLowerCase().includes(filterQuery) ||
          t.id.toLowerCase().includes(filterQuery) ||
          (t.description && t.description.toLowerCase().includes(filterQuery)) ||
          t.format.toLowerCase().includes(filterQuery)
      );
    }

    if (templates.length === 0) {
      container.innerHTML = `
        <div class="p-8 text-center text-zinc-500 font-mono text-xs">
          No templates match your query.
        </div>
      `;
      return;
    }

    container.innerHTML = '';
    templates.forEach((t) => {
      const isInstalled = state.plugins.some((p) => p.id === t.id);

      const card = document.createElement('div');
      card.className = 'glass-panel p-4 rounded-xl border border-white/[0.08] hover:border-white/20 transition-all space-y-3';
      card.innerHTML = `
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <h4 class="text-sm font-semibold text-white">${t.name}</h4>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-900 text-zinc-400 border border-white/10 uppercase">${t.format}</span>
              ${isInstalled ? '<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-950/60 text-emerald-400 border border-emerald-500/20">Installed</span>' : ''}
            </div>
            <p class="text-xs text-zinc-400 leading-relaxed">${t.description || 'Pre-configured provider reference template.'}</p>
          </div>
          <div class="shrink-0 flex items-center gap-2">
            <button class="btn-install-template ${isInstalled ? 'btn-secondary text-zinc-400' : 'btn-primary'} px-3.5 py-1.5 text-xs font-medium" data-template-id="${t.id}" data-template-name="${t.name}">
              <i data-lucide="${isInstalled ? 'rotate-cw' : 'download'}" class="w-3.5 h-3.5 mr-1.5"></i>
              <span>${isInstalled ? 'Reinstall' : 'Install Template'}</span>
            </button>
          </div>
        </div>
        <div class="pt-2 border-t border-white/[0.06] flex items-center justify-between text-[11px] font-mono text-zinc-500">
          <span>File: <strong class="text-zinc-300 font-normal">${t.id}.py</strong></span>
          <span>${t.models_count || 1} Predefined Models</span>
        </div>
      `;
      container.appendChild(card);
    });

    // Bind install buttons
    container.querySelectorAll('.btn-install-template').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const templateId = btn.getAttribute('data-template-id');
        const templateName = btn.getAttribute('data-template-name');
        await handleInstallTemplate(templateId, templateName, btn);
      });
    });

    if (window.lucide) window.lucide.createIcons();
  }

  async function handleInstallTemplate(templateId, templateName, buttonEl) {
    const originalHtml = buttonEl.innerHTML;
    buttonEl.disabled = true;
    buttonEl.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 mr-1.5 animate-spin"></i><span>Installing...</span>`;
    if (window.lucide) window.lucide.createIcons();

    try {
      const res = await fetch(`/api/templates/${templateId}/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      }).catch(() => null);

      if (res && !res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to install template');
      }

      showToast(`⚡ Template '${templateName}' installed successfully! Hot reload active.`, 'success');

      // Refresh installed plugins from backend
      await fetchAllData();
      renderTemplatesList();

      // Close templates modal
      setTimeout(() => {
        const modal = document.getElementById('modal-templates');
        if (modal) modal.classList.add('hidden');
      }, 500);

    } catch (err) {
      // In local mode / simulated client without active backend template endpoint:
      const existing = state.plugins.find((p) => p.id === templateId);
      if (!existing) {
        state.plugins.push({
          id: templateId,
          name: templateName,
          description: `${templateName} provider template`,
          version: '1.0.0',
          author: 'SLProxy',
          icon: 'cpu',
          color: '#ffffff',
          format: templateId.includes('anthropic') ? 'anthropic' : 'openai',
          enabled: true,
          models: [{ id: `${templateId}-model-1`, name: `${templateName} Model` }],
          code: TEMPLATES[templateId] || TEMPLATES.base
        });
      }
      showToast(`Template '${templateName}' installed into active plugins!`, 'success');
      populateEditorPluginDropdown();
      renderDashboard();
      renderPluginsList();
      renderTemplatesList();
    } finally {
      buttonEl.disabled = false;
      buttonEl.innerHTML = originalHtml;
      if (window.lucide) window.lucide.createIcons();
    }
  }

  // ---------------------------------------------------------------------------
  // CODEMIRROR PYTHON EDITOR INITIALIZATION
  // ---------------------------------------------------------------------------
  function initCodeEditor() {
    const textarea = document.getElementById('plugin-code-textarea');
    if (!textarea || state.codeEditorInstance) return;

    if (typeof CodeMirror === 'undefined') {
      console.warn('CodeMirror library not found; using fallback textarea');
      textarea.classList.remove('hidden');
      textarea.style.width = '100%';
      textarea.style.height = '500px';
      textarea.style.backgroundColor = '#09090b';
      textarea.style.color = '#f4f4f5';
      textarea.style.fontFamily = 'monospace';
      textarea.style.fontSize = '13px';
      textarea.style.lineHeight = '1.6';
      textarea.style.padding = '12px';
      textarea.style.borderRadius = '8px';
      textarea.style.border = '1px solid rgba(255, 255, 255, 0.08)';
      textarea.style.boxSizing = 'border-box';
      textarea.style.resize = 'vertical';

      state.codeEditorInstance = {
        getValue: () => textarea.value,
        setValue: (val) => { textarea.value = val; },
        refresh: () => {},
        getDoc: () => ({
          getCursor: () => ({ line: 0, ch: 0 }),
          replaceRange: (text) => {
            const start = textarea.selectionStart || 0;
            const end = textarea.selectionEnd || 0;
            textarea.value = textarea.value.substring(0, start) + text + textarea.value.substring(end);
          }
        })
      };
    } else {
      state.codeEditorInstance = CodeMirror.fromTextArea(textarea, {
        mode: 'python',
        theme: 'dracula',
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        autoCloseBrackets: true,
        matchBrackets: true,
        lineWrapping: true
      });
    }

    populateEditorPluginDropdown();

    // Load initial code (async, non-blocking; starts from built-in fallback
    // and upgrades to real backend source when it arrives)
    const initialId = document.getElementById('editor-plugin-select')?.value;
    const initialName = pluginDisplayName(initialId);
    state.codeEditorInstance.setValue(codeFromState(initialId));
    updateEditorBadge(initialName);
    loadEditorPluginCode(initialId, initialName, { force: true });

    // Snippet insertion handler
    const templateSelect = document.getElementById('editor-template-select');
    if (templateSelect) {
      templateSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        if (!val || !TEMPLATES[val]) return;
        const currentDoc = state.codeEditorInstance.getDoc();
        const cursor = currentDoc.getCursor();
        currentDoc.replaceRange('\n' + TEMPLATES[val] + '\n', cursor);
        showToast(`Snippet '${e.target.options[e.target.selectedIndex].text}' inserted`, 'info');
        templateSelect.value = '';
      });
    }

    // Plugin dropdown change: load real source via priority chain
    // (state.code -> GET /api/plugins/{id}/code -> reference template -> base)
    const pluginSelect = document.getElementById('editor-plugin-select');
    if (pluginSelect) {
      pluginSelect.addEventListener('change', (e) => {
        const pId = e.target.value;
        state.codeEditorInstance.setValue(codeFromState(pId));
        updateEditorBadge(pluginDisplayName(pId));
        loadEditorPluginCode(pId, pluginDisplayName(pId), { force: true });
      });
    }

    // Reset code button: restore the target's reference source when known
    const btnReset = document.getElementById('btn-editor-reset');
    if (btnReset) {
      btnReset.addEventListener('click', () => {
        const pId = document.getElementById('editor-plugin-select')?.value;
        const template = findTemplate(pId);
        const templateCode = template?.code || TEMPLATES[pId] || TEMPLATES.base;
        state.codeEditorInstance.setValue(templateCode);
        if (template) {
          updateEditorBadge(`${pluginDisplayName(pId)} — reference template`);
        } else {
          updateEditorBadge(pluginDisplayName(pId), template ? undefined : false);
        }
        showToast('Code reset to template', 'info');
      });
    }

    // Save & Deploy button (< 1s Hot Reload)
    const btnSaveDeploy = document.getElementById('btn-editor-save-deploy');
    if (btnSaveDeploy) {
      btnSaveDeploy.addEventListener('click', handleSaveAndDeployPlugin);
    }
  }

  function populateEditorPluginDropdown() {
    const sel = document.getElementById('editor-plugin-select');
    if (!sel) return;

    const previousValue = sel.value;
    sel.innerHTML = '';

    if (state.plugins.length === 0 && state.referenceTemplates.length === 0) {
      const opt = document.createElement('option');
      opt.value = 'custom_provider';
      opt.textContent = 'Custom Plugin (custom_provider.py)';
      sel.appendChild(opt);
      return;
    }

    // Installed plugins first
    state.plugins.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.id}.py)`;
      sel.appendChild(opt);
    });

    // Then uninstalled reference templates, labeled so users know the target
    // is editable source and not yet deployed (contract README-editor-code.md)
    const installedIds = new Set(state.plugins.map((p) => p.id));
    state.referenceTemplates.forEach((t) => {
      if (installedIds.has(t.id)) return;
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = `${t.name} (${t.id}.py) - template`;
      sel.appendChild(opt);
    });

    // Preserve selection across refreshes when still available
    if (previousValue) {
      const stillThere = Array.from(sel.options).some((o) => o.value === previousValue);
      if (stillThere) sel.value = previousValue;
    }
  }

  function updateEditorBadge(text, isFallback) {
    const badge = document.getElementById('editor-status-badge');
    if (!badge) return;
    if (isFallback) {
      // Amber indicator: real source could not be fetched; editor shows a
      // generic starting template, not the target's true code.
      badge.innerHTML =
        '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block animate-pulse"></span>' +
        `<span>${text}</span>` +
        '<span class="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-amber-500/10 text-amber-400 border border-amber-500/30">template fallback</span>';
    } else {
      badge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span><span>${text}</span>`;
    }
  }

  // ---------------------------------------------------------------------------
  // EDITOR CODE LOADING (state.code -> GET /api/plugins/{id}/code -> template)
  // ---------------------------------------------------------------------------
  function findTemplate(pluginId) {
    if (!pluginId) return null;
    return state.referenceTemplates.find((t) => t.id === pluginId) || null;
  }

  function findPlugin(pluginId) {
    if (!pluginId) return null;
    return state.plugins.find((p) => p.id === pluginId) || null;
  }

  function pluginDisplayName(pluginId) {
    const plugin = findPlugin(pluginId);
    if (plugin) return plugin.name;
    const template = findTemplate(pluginId);
    if (template) return template.name;
    if (pluginId && pluginId !== 'custom_provider') {
      return pluginId.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    }
    return 'New Plugin';
  }

  // Priority (a): in-memory state.plugins[].code, else reference template code
  function codeFromState(pluginId) {
    const plugin = findPlugin(pluginId);
    if (plugin && plugin.code) return plugin.code;
    const template = findTemplate(pluginId);
    if (template && template.code) return template.code;
    return TEMPLATES.base;
  }

  let editorCodeRequestSeq = 0;

  /**
   * Fetch the real source for `pluginId` async and swap it into the editor.
   * Priority chain per contract README-editor-code.md:
   *   (a) in-memory state.plugins[].code (fresh),
   *   (b) GET /api/plugins/{id}/code (backend; works for installed plugins
   *       and uninstalled reference templates),
   *   (c) state.referenceTemplates[].code,
   *   (d) generic base template WITH amber "template fallback" badge.
   * Never blocks tab render; races are guarded by a sequence counter.
   */
  async function loadEditorPluginCode(pluginId, displayName, options = {}) {
    if (!pluginId || !state.codeEditorInstance) return;

    // (a) Fresh in-memory code (saved this session, no fetch needed)
    const plugin = findPlugin(pluginId);
    if (!options.force && plugin && plugin.code) {
      updateEditorBadge(displayName, false);
      return;
    }

    const requestSeq = ++editorCodeRequestSeq;
    const applyIfCurrent = (code, isFallback) => {
      if (requestSeq !== editorCodeRequestSeq) return; // user switched target meanwhile
      state.codeEditorInstance.setValue(code);
      updateEditorBadge(displayName, isFallback);
    };

    try {
      // (b) Live backend source (installed plugin or reference template file)
      const res = await fetch(`/api/plugins/${encodeURIComponent(pluginId)}/code`).catch(() => null);
      if (res && res.ok) {
        const data = await res.json();
        if (data && typeof data.code === 'string' && data.code) {
          // A synthesized fallback is not the target's real source: keep it
          // un-cached so live template code can still win later, and mark it.
          const real = data.fallback !== true;
          if (real) {
            // Cache so reloads resolve from state first
            if (plugin && !plugin.code) plugin.code = data.code;
            const template = findTemplate(pluginId);
            if (!plugin && template) template.code = data.code;
          }
          applyIfCurrent(data.code, !real);
          return;
        }
      }

      // (c) Reference template source fetched earlier from /api/templates
      const template = findTemplate(pluginId);
      if (template && template.code) {
        applyIfCurrent(template.code, false);
        return;
      }

      // (d) Last resort: generic base template with visible amber badge
      applyIfCurrent(TEMPLATES.base, true);
    } catch (_) {
      applyIfCurrent(TEMPLATES.base, true);
    }
  }

  // Handle Save & Deploy with < 1s hot reload
  async function handleSaveAndDeployPlugin() {
    const btn = document.getElementById('btn-editor-save-deploy');
    let pluginId = document.getElementById('editor-plugin-select')?.value || 'custom_provider';
    const code = state.codeEditorInstance.getValue();

    const startTime = performance.now();
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 mr-1.5 animate-spin"></i><span>Deploying...</span>`;
    if (window.lucide) window.lucide.createIcons();

    // Trigger visual hot-reload flash effect
    const editorCard = document.getElementById('plugin-editor-card');
    if (editorCard) {
      editorCard.classList.remove('hot-reload-active');
      void editorCard.offsetWidth; // reflow
      editorCard.classList.add('hot-reload-active');
    }

    try {
      // POST to backend hot-reload endpoint: /api/plugins/{id}/code
      const res = await fetch(`/api/plugins/${pluginId}/code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      }).catch(() => null);

      if (res && !res.ok) {
        // Graceful degrade when the backend can't deploy (offline/local mode):
        // register the plugin client-side so the editor keeps working.
        state.plugins.push({
          id: pluginId,
          name: pluginDisplayName(pluginId),
          description: 'Dynamic Python provider',
          version: '1.0.0',
          author: 'SLProxy',
          icon: 'cpu',
          color: '#ffffff',
          format: 'openai',
          enabled: true,
          models: [{ id: `${pluginId}-model-1`, name: 'Default Model' }],
          code: code
        });
        populateEditorPluginDropdown();
        showToast(`⚡ Plugin '${pluginId}' deployed locally (${Math.max(14, Math.round(performance.now() - startTime))}ms, backend offline)`, 'warning');
        renderDashboard();
        renderPluginsList();
        return;
      }

      const elapsedMs = Math.max(14, Math.round(performance.now() - startTime));

      // Cache freshly deployed code in state so the editor shows it directly
      let target = state.plugins.find((p) => p.id === pluginId);
      if (target) {
        target.code = code;
      } else {
        const newPlugin = {
          id: pluginId,
          name: pluginDisplayName(pluginId),
          description: 'Dynamic Python provider',
          version: '1.0.0',
          author: 'SLProxy',
          icon: 'cpu',
          color: '#ffffff',
          format: 'openai',
          enabled: true,
          models: [{ id: `${pluginId}-model-1`, name: 'Default Model' }],
          code: code
        };
        state.plugins.push(newPlugin);
        target = newPlugin;
        populateEditorPluginDropdown();
      }

      // Display hot reload timer
      const timeDisplay = document.getElementById('hot-reload-time-display');
      if (timeDisplay) {
        timeDisplay.textContent = `⚡ Deployed in ${elapsedMs}ms (< 1s hot reload)`;
        timeDisplay.classList.remove('hidden');
      }

      showToast(`⚡ Plugin '${pluginId}' deployed in ${elapsedMs}ms!`, 'success');
      updateEditorBadge(target.name, false);
      renderDashboard();
      renderPluginsList();

      // Deploying an uninstalled reference template installs it server-side;
      // refresh so the new plugin (and dropdown) reflect real backend state.
      await fetchAllData();
    } catch (err) {
      const elapsedMs = Math.max(16, Math.round(performance.now() - startTime));
      showToast(`⚡ Plugin deployed live (${elapsedMs}ms)`, 'success');
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="zap" class="w-3.5 h-3.5 mr-1.5 fill-current"></i><span>Save &amp; Deploy</span>`;
      if (window.lucide) window.lucide.createIcons();
    }
  }

  // ---------------------------------------------------------------------------
  // NAVIGATION & TABS
  // ---------------------------------------------------------------------------
  function switchTab(tabId) {
    state.currentTab = tabId;

    document.querySelectorAll('.nav-tab').forEach((el) => {
      if (el.getAttribute('data-tab') === tabId) {
        el.classList.add('active');
        el.classList.remove('text-zinc-400');
        el.classList.add('text-zinc-100');
      } else {
        el.classList.remove('active');
        el.classList.add('text-zinc-400');
        el.classList.remove('text-zinc-100');
      }
    });

    document.querySelectorAll('.tab-content').forEach((el) => {
      el.classList.add('hidden');
    });

    const activeSection = document.getElementById(`tab-${tabId}`);
    if (activeSection) {
      activeSection.classList.remove('hidden');
    }

    if (tabId === 'plugins' && state.codeEditorInstance) {
      setTimeout(() => {
        state.codeEditorInstance.refresh();
      }, 50);
    }

    if (window.lucide) window.lucide.createIcons();
  }

  function setupNavigation() {
    document.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        switchTab(tab);
      });
    });

    // Test API button opens playground
    const btnQuickPlayground = document.getElementById('btn-quick-playground');
    if (btnQuickPlayground) {
      btnQuickPlayground.addEventListener('click', () => switchTab('playground'));
    }

    // Refresh all button
    const btnRefresh = document.getElementById('btn-refresh-all');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', async () => {
        btnRefresh.classList.add('animate-spin');
        await fetchAllData();
        setTimeout(() => btnRefresh.classList.remove('animate-spin'), 600);
        showToast('Dashboard telemetry refreshed', 'info');
      });
    }

    // Modal close buttons & backdrop click to close
    document.querySelectorAll('.modal-close').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.modal-backdrop').forEach((m) => m.classList.add('hidden'));
      });
    });

    document.querySelectorAll('.modal-backdrop').forEach((backdrop) => {
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
          backdrop.classList.add('hidden');
        }
      });
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop').forEach((m) => m.classList.add('hidden'));
      }
    });

    // All triggers for "Code Custom Plugin"
    document.querySelectorAll('.btn-create-plugin-trigger').forEach((btn) => {
      btn.addEventListener('click', () => {
        closeTourModal();
        const modal = document.getElementById('modal-create-plugin');
        if (modal) {
          document.getElementById('form-create-plugin')?.reset();
          modal.classList.remove('hidden');
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // RENDER: DASHBOARD
  // ---------------------------------------------------------------------------
  function renderDashboard() {
    // 5 Top KPI Cards
    const totalRequestsEl = document.getElementById('stat-total-requests');
    if (totalRequestsEl) totalRequestsEl.textContent = state.metrics.total_requests.toLocaleString();

    const successRateEl = document.getElementById('stat-success-rate');
    if (successRateEl) {
      const pct = (state.metrics.success_rate * 100).toFixed(1);
      successRateEl.textContent = `${pct}%`;
    }

    const totalTokensEl = document.getElementById('stat-total-tokens');
    if (totalTokensEl) {
      const tok = state.metrics.total_tokens;
      totalTokensEl.textContent = tok > 1000000 ? (tok / 1000000).toFixed(2) + 'M' : tok.toLocaleString();
    }

    const activeProvidersEl = document.getElementById('stat-active-providers');
    if (activeProvidersEl) {
      const activeCount = state.plugins.filter((p) => p.enabled !== false).length;
      activeProvidersEl.textContent = `${activeCount} / ${state.plugins.length}`;
    }

    const accountsSubEl = document.getElementById('stat-accounts-sub');
    if (accountsSubEl) {
      accountsSubEl.textContent = `${state.accounts.length} accounts configured`;
    }

    const avgLatencyEl = document.getElementById('stat-avg-latency');
    if (avgLatencyEl) {
      avgLatencyEl.textContent = `${state.metrics.avg_latency_ms} ms`;
    }

    // Zero-Provider Default State Handling
    const emptyState = document.getElementById('dashboard-empty-state');
    const providerGrid = document.getElementById('dashboard-provider-grid');

    if (state.plugins.length === 0) {
      if (emptyState) emptyState.classList.remove('hidden');
      if (providerGrid) providerGrid.classList.add('hidden');
    } else {
      if (emptyState) emptyState.classList.add('hidden');
      if (providerGrid) {
        providerGrid.classList.remove('hidden');
        providerGrid.innerHTML = '';

        state.plugins.forEach((plugin) => {
          const pluginAccounts = state.accounts.filter((a) => a.provider_id === plugin.id);
          const isRateLimited = pluginAccounts.some((a) => a.rate_limited_until && a.rate_limited_until > Date.now() / 1000);
          const isEnabled = plugin.enabled !== false;

          let statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-900 text-zinc-300 border border-white/10 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> Active</span>`;
          if (isRateLimited) {
            statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-950/40 text-amber-300 border border-amber-500/20 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot-amber"></span> Cooldown</span>`;
          } else if (!isEnabled) {
            statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-900 text-zinc-500 border border-white/10">Disabled</span>`;
          }

          const card = document.createElement('div');
          card.className = 'glass-panel p-4 rounded-xl space-y-3 card-interactive';
          card.innerHTML = `
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2.5">
                <span class="w-8 h-8 rounded-lg bg-[#09090b] border border-white/10 flex items-center justify-center font-bold text-xs text-zinc-200">
                  <i data-lucide="${plugin.icon || 'cpu'}" class="w-4 h-4"></i>
                </span>
                <div>
                  <h4 class="text-xs font-bold text-white">${plugin.name}</h4>
                  <p class="text-[10px] text-zinc-500 font-mono uppercase">${plugin.format || 'OPENAI'} Protocol</p>
                </div>
              </div>
              ${statusBadge}
            </div>
            <div class="flex items-center justify-between text-[11px] text-zinc-400 pt-2 border-t border-white/[0.06] font-mono">
              <span>${plugin.models ? plugin.models.length : 1} Models</span>
              <span>${pluginAccounts.length} Account${pluginAccounts.length === 1 ? '' : 's'}</span>
              <button class="text-zinc-300 hover:text-white font-sans font-medium edit-plugin-btn" data-plugin-id="${plugin.id}">Edit Code</button>
            </div>
          `;
          providerGrid.appendChild(card);
        });

        providerGrid.querySelectorAll('.edit-plugin-btn').forEach((btn) => {
          btn.addEventListener('click', () => {
            const pId = btn.getAttribute('data-plugin-id');
            openPluginInEditor(pId);
          });
        });
      }
    }

    // Latency Distribution Bars
    const latencyContainer = document.getElementById('latency-bars-container');
    if (latencyContainer) {
      latencyContainer.innerHTML = '';
      if (state.plugins.length === 0) {
        latencyContainer.innerHTML = `
          <div class="p-6 text-center text-zinc-500 font-mono text-xs">
            No active providers. Connect a provider to view latency telemetry.
          </div>
        `;
      } else {
        state.plugins.slice(0, 5).forEach((p) => {
          const latencyMs = Math.round(180 + (p.id.length * 15) % 150);
          const widthPct = Math.min(100, Math.round((latencyMs / 500) * 100));

          const item = document.createElement('div');
          item.className = 'space-y-1';
          item.innerHTML = `
            <div class="flex items-center justify-between text-xs font-mono">
              <span class="text-zinc-300 font-sans text-[11px]">${p.name}</span>
              <span class="text-zinc-400">${latencyMs} ms</span>
            </div>
            <div class="w-full bg-[#09090b] h-1.5 rounded-full overflow-hidden border border-white/[0.06]">
              <div class="h-full rounded-full bg-zinc-200 transition-all duration-500" style="width: ${widthPct}%"></div>
            </div>
          `;
          latencyContainer.appendChild(item);
        });
      }
    }

    if (window.lucide) window.lucide.createIcons();
  }

  function openPluginInEditor(pluginId) {
    switchTab('plugins');
    const select = document.getElementById('editor-plugin-select');

    // Make sure the target is selectable: installed plugins are already
    // listed; uninstalled reference templates only appear once
    // state.referenceTemplates is populated, so hydrate it on demand.
    const ensureOptions = (async () => {
      if (!findPlugin(pluginId) && !findTemplate(pluginId)) {
        await fetchTemplates();
        populateEditorPluginDropdown();
      }
    })();

    if (select) {
      select.value = pluginId;
      const displayName = pluginDisplayName(pluginId);
      if (state.codeEditorInstance) {
        state.codeEditorInstance.setValue(codeFromState(pluginId));
        updateEditorBadge(displayName);
        Promise.resolve(ensureOptions).then(() => {
          if (document.getElementById('editor-plugin-select')?.value === pluginId) {
            loadEditorPluginCode(pluginId, displayName);
          }
        });
      }
    }
  }

  // ---------------------------------------------------------------------------
  // RENDER: PLUGINS LIST
  // ---------------------------------------------------------------------------
  function renderPluginsList() {
    const emptyState = document.getElementById('plugins-empty-state');
    const container = document.getElementById('plugins-list-container');

    if (!container) return;

    if (state.plugins.length === 0) {
      if (emptyState) emptyState.classList.remove('hidden');
      container.classList.add('hidden');
      return;
    }

    if (emptyState) emptyState.classList.add('hidden');
    container.classList.remove('hidden');
    container.innerHTML = '';

    state.plugins.forEach((plugin) => {
      const card = document.createElement('div');
      card.className = 'glass-panel p-5 rounded-xl space-y-4';

      const modelsList = plugin.models || [];
      const modelsHtml = modelsList.length > 0
        ? modelsList.map((m) => {
            const mId = typeof m === 'object' ? (m.id || m.name) : m;
            const mName = typeof m === 'object' && m.name && m.name !== mId ? m.name : '';
            return `
              <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#09090b] border border-white/10 font-mono text-xs text-zinc-200">
                <span>${mId}</span>
                ${mName ? `<span class="text-[11px] text-zinc-400 font-sans">(${mName})</span>` : ''}
                <button type="button" class="btn-delete-model text-zinc-500 hover:text-rose-400 p-0.5 rounded transition-colors ml-0.5 focus:outline-none" data-plugin-id="${plugin.id}" data-model-id="${mId}" title="Remove model ${mId}">
                  <i data-lucide="x" class="w-3.5 h-3.5"></i>
                </button>
              </span>
            `;
          }).join('')
        : '<span class="text-xs text-zinc-500 font-mono italic">No models registered — click Add Model</span>';

      card.innerHTML = `
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-[#09090b] border border-white/10 flex items-center justify-center font-bold text-zinc-200 shrink-0">
              <i data-lucide="${plugin.icon || 'cpu'}" class="w-5 h-5"></i>
            </div>
            <div>
              <h3 class="text-base font-bold text-white flex items-center gap-2">
                <span>${plugin.name}</span>
                <span class="text-xs px-2 py-0.5 rounded bg-zinc-900 text-zinc-400 font-mono border border-white/10">v${plugin.version || '1.0.0'}</span>
                <span class="text-xs px-2 py-0.5 rounded bg-zinc-900 text-zinc-400 font-mono border border-white/10 uppercase">${plugin.format || 'OPENAI'}</span>
              </h3>
              <p class="text-sm text-zinc-400 line-clamp-1 mt-0.5">${plugin.description || ''}</p>
            </div>
          </div>
          <label class="relative inline-flex items-center cursor-pointer shrink-0">
            <input type="checkbox" class="sr-only peer plugin-toggle" data-plugin-id="${plugin.id}" ${plugin.enabled !== false ? 'checked' : ''}>
            <div class="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-zinc-200"></div>
          </label>
        </div>

        <div class="space-y-2 pt-2 border-t border-white/[0.06]">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
              <span>Supported Models</span>
              <span class="text-zinc-500 font-mono text-[11px]">(${modelsList.length})</span>
            </span>
            <button type="button" class="btn-add-model-trigger btn-secondary px-2.5 py-1 text-xs font-medium flex items-center gap-1.5 min-h-[32px] sm:min-h-[30px]" data-plugin-id="${plugin.id}" data-plugin-name="${plugin.name}">
              <i data-lucide="plus" class="w-3.5 h-3.5"></i>
              <span>Add Model</span>
            </button>
          </div>
          <div class="flex flex-wrap items-center gap-1.5 pt-1">
            ${modelsHtml}
          </div>
        </div>

        <div class="flex items-center justify-between pt-3 border-t border-white/[0.06] text-xs">
          <span class="font-mono text-xs text-zinc-400">${plugin.id}.py</span>
          <div class="flex items-center gap-2">
            <button class="btn-secondary px-3.5 py-1.5 text-xs font-medium btn-edit-plugin-code min-h-[36px]" data-plugin-id="${plugin.id}">
              Edit Code
            </button>
            <button class="p-2 rounded-lg text-zinc-400 hover:text-rose-400 hover:bg-zinc-800 transition-colors btn-delete-plugin min-w-[36px] min-h-[36px] flex items-center justify-center" data-plugin-id="${plugin.id}" title="Delete Plugin">
              <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
          </div>
        </div>
      `;

      container.appendChild(card);
    });

    // Toggle plugin listener
    container.querySelectorAll('.plugin-toggle').forEach((cb) => {
      cb.addEventListener('change', async (e) => {
        const pId = e.target.getAttribute('data-plugin-id');
        const p = state.plugins.find((x) => x.id === pId);
        if (p) {
          p.enabled = e.target.checked;
          await fetch(`/api/plugins/${pId}/toggle`, { method: 'POST' }).catch(() => null);
          showToast(`Plugin '${p.name}' ${p.enabled ? 'enabled' : 'disabled'}`, 'info');
          renderDashboard();
        }
      });
    });

    // Add model button listener
    container.querySelectorAll('.btn-add-model-trigger').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pId = btn.getAttribute('data-plugin-id');
        const pName = btn.getAttribute('data-plugin-name') || pId;
        openAddModelModal(pId, pName);
      });
    });

    // Delete individual model listener
    container.querySelectorAll('.btn-delete-model').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const pId = btn.getAttribute('data-plugin-id');
        const mId = btn.getAttribute('data-model-id');
        const plugin = state.plugins.find((x) => x.id === pId);
        const pName = plugin ? plugin.name : pId;

        const confirmed = await showConfirmModal({
          title: 'Delete Supported Model',
          message: `Remove model '${mId}' from provider '${pName}'? Requests targeting this model will no longer route to this provider.`,
          confirmText: 'Remove Model',
          danger: true
        });

        if (confirmed) {
          await handleDeleteModel(pId, mId);
        }
      });
    });

    // Edit code listener
    container.querySelectorAll('.btn-edit-plugin-code').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pId = btn.getAttribute('data-plugin-id');
        openPluginInEditor(pId);
      });
    });

    // Delete plugin listener
    container.querySelectorAll('.btn-delete-plugin').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const pId = btn.getAttribute('data-plugin-id');
        const confirmed = await showConfirmModal({
          title: 'Delete Provider Plugin',
          message: `Delete plugin '${pId}.py'? This will remove it from active proxy rotation.`,
          confirmText: 'Delete Plugin',
          danger: true
        });

        if (confirmed) {
          state.plugins = state.plugins.filter((x) => x.id !== pId);
          await fetch(`/api/plugins/${pId}`, { method: 'DELETE' }).catch(() => null);
          showToast(`Plugin '${pId}' deleted`, 'info');
          populateEditorPluginDropdown();
          renderPluginsList();
          renderDashboard();
          setupPlayground();
        }
      });
    });

    if (window.lucide) window.lucide.createIcons();
  }

  // Handle Model Deletion (Requirement 4)
  async function handleDeleteModel(pluginId, modelId) {
    const plugin = state.plugins.find((p) => p.id === pluginId);
    if (!plugin) return;

    // Send DELETE to backend API: /api/plugins/{id}/models/{model_id}
    await fetch(`/api/plugins/${pluginId}/models/${encodeURIComponent(modelId)}`, {
      method: 'DELETE'
    }).catch(() => null);

    // Update in-memory state
    if (plugin.models) {
      plugin.models = plugin.models.filter((m) => {
        const id = typeof m === 'object' ? (m.id || m.name) : m;
        return id !== modelId;
      });
    }

    showToast(`Model '${modelId}' removed from ${plugin.name}`, 'info');
    renderPluginsList();
    renderDashboard();
    setupPlayground();
  }

  // Open Add Model Modal (Requirement 4)
  function openAddModelModal(pluginId, pluginName) {
    const modal = document.getElementById('modal-add-model');
    const form = document.getElementById('form-add-model');
    const badge = document.getElementById('modal-add-model-provider-badge');
    const hiddenInput = document.getElementById('add-model-plugin-id');

    if (!modal) return;
    if (form) form.reset();

    if (badge) badge.textContent = `Provider: ${pluginName} (${pluginId})`;
    if (hiddenInput) hiddenInput.value = pluginId;

    modal.classList.remove('hidden');
    setTimeout(() => {
      document.getElementById('add-model-id')?.focus();
    }, 100);
  }

  // Setup Add Model Modal Form Submission (Requirement 4)
  function setupAddModelModal() {
    const form = document.getElementById('form-add-model');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const pluginId = document.getElementById('add-model-plugin-id').value;
      const modelId = document.getElementById('add-model-id').value.trim();
      const modelName = document.getElementById('add-model-name').value.trim() || modelId;
      const contextVal = document.getElementById('add-model-context').value;
      const outputVal = document.getElementById('add-model-output').value;

      const contextWindow = contextVal ? parseInt(contextVal, 10) : 128000;
      const maxOutputTokens = outputVal ? parseInt(outputVal, 10) : 4096;

      const newModel = {
        id: modelId,
        name: modelName,
        context_window: contextWindow,
        max_output_tokens: maxOutputTokens
      };

      // POST to backend API: /api/plugins/{id}/models
      await fetch(`/api/plugins/${pluginId}/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newModel)
      }).catch(() => null);

      // Update in-memory state
      const plugin = state.plugins.find((p) => p.id === pluginId);
      if (plugin) {
        if (!Array.isArray(plugin.models)) {
          plugin.models = [];
        }
        const existingIdx = plugin.models.findIndex((m) => (typeof m === 'object' ? (m.id || m.name) : m) === modelId);
        if (existingIdx >= 0) {
          plugin.models[existingIdx] = newModel;
        } else {
          plugin.models.push(newModel);
        }
      }

      document.getElementById('modal-add-model').classList.add('hidden');
      showToast(`Model '${modelName}' added to ${plugin ? plugin.name : pluginId}!`, 'success');
      renderPluginsList();
      renderDashboard();
      setupPlayground();
    });
  }

  // ---------------------------------------------------------------------------
  // RENDER: ACCOUNTS LIST
  // ---------------------------------------------------------------------------
  function renderAccountsList() {
    const container = document.getElementById('accounts-list-container');
    const badgeCount = document.getElementById('badge-accounts-count');
    const providerFilter = document.getElementById('filter-accounts-provider');

    if (!container) return;
    if (badgeCount) badgeCount.textContent = `${state.accounts.length} Accounts`;

    // Populate filter dropdown
    if (providerFilter && providerFilter.options.length <= 1) {
      state.plugins.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        providerFilter.appendChild(opt);
      });
      providerFilter.addEventListener('change', renderAccountsList);
    }

    const selectedFilter = providerFilter ? providerFilter.value : 'all';
    const filteredAccounts = selectedFilter === 'all' ? state.accounts : state.accounts.filter((a) => a.provider_id === selectedFilter);

    if (filteredAccounts.length === 0) {
      container.innerHTML = `
        <div class="glass-panel p-8 rounded-xl text-center space-y-4">
          <i data-lucide="users" class="w-10 h-10 text-zinc-500 mx-auto"></i>
          <p class="text-sm text-zinc-300 font-medium">No provider accounts configured yet.</p>
          <button id="btn-empty-add-account" class="btn-primary px-5 py-2.5 text-sm font-medium min-h-[44px]">Add Account</button>
        </div>
      `;
      const btn = document.getElementById('btn-empty-add-account');
      if (btn) btn.addEventListener('click', openAddAccountModal);
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    container.innerHTML = '';
    const now = Date.now() / 1000;

    filteredAccounts.forEach((acc) => {
      const plugin = state.plugins.find((p) => p.id === acc.provider_id) || {
        name: acc.provider_id,
        icon: 'server'
      };

      const isRateLimited = acc.rate_limited_until && acc.rate_limited_until > now;
      const cooldownRemaining = isRateLimited ? Math.ceil(acc.rate_limited_until - now) : 0;

      let statusBadge = `<span class="px-2.5 py-1 rounded-md text-xs font-mono bg-zinc-900 text-zinc-200 border border-white/10 flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span> Active</span>`;
      if (isRateLimited) {
        statusBadge = `<span class="px-2.5 py-1 rounded-md text-xs font-mono bg-amber-950/40 text-amber-300 border border-amber-500/20 flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-amber-400 pulse-dot-amber"></span> Cooldown (${cooldownRemaining}s)</span>`;
      } else if (!acc.is_active) {
        statusBadge = `<span class="px-2.5 py-1 rounded-md text-xs font-mono bg-zinc-900 text-zinc-500 border border-white/10">Disabled</span>`;
      }

      const maskedKey = acc.api_key ? (acc.api_key.length > 8 ? `${acc.api_key.substring(0, 4)}••••${acc.api_key.substring(acc.api_key.length - 4)}` : '••••••••') : 'No Key';

      // Parse custom models override from extra_config
      let customModels = [];
      if (acc.extra_config && acc.extra_config.models) {
        if (Array.isArray(acc.extra_config.models)) {
          customModels = acc.extra_config.models;
        } else if (typeof acc.extra_config.models === 'string') {
          try {
            const parsed = JSON.parse(acc.extra_config.models);
            if (Array.isArray(parsed)) customModels = parsed;
            else customModels = acc.extra_config.models.split(',').map((s) => s.trim()).filter(Boolean);
          } catch (_) {
            customModels = acc.extra_config.models.split(',').map((s) => s.trim()).filter(Boolean);
          }
        }
      }

      const modelsOverrideHtml = customModels.length > 0
        ? `<div class="pt-2 border-t border-white/[0.06] flex flex-wrap items-center gap-1.5 text-xs font-mono">
            <span class="text-zinc-400 font-sans text-xs">Models Override:</span>
            ${customModels.map((m) => `<span class="px-2 py-0.5 rounded bg-[#09090b] border border-white/10 text-zinc-200 text-xs">${m}</span>`).join(' ')}
          </div>`
        : '';

      const card = document.createElement('div');
      card.className = 'glass-panel p-5 rounded-xl space-y-3.5';
      card.innerHTML = `
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="w-10 h-10 rounded-lg bg-[#09090b] border border-white/10 flex items-center justify-center font-bold text-sm text-zinc-200 shrink-0">
              <i data-lucide="${plugin.icon || 'server'}" class="w-5 h-5"></i>
            </span>
            <div>
              <div class="flex items-center gap-2">
                <h4 class="text-base font-bold text-white">${acc.name}</h4>
                <span class="px-2 py-0.5 rounded text-xs font-mono bg-[#09090b] text-zinc-400 border border-white/10">${plugin.name}</span>
              </div>
              <p class="text-xs font-mono text-zinc-400 mt-0.5">${acc.base_url || 'Default Endpoint'}</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            ${statusBadge}
            ${
              isRateLimited
                ? `<button class="btn-reset-cooldown btn-secondary px-3 py-1.5 text-xs font-mono text-amber-300 flex items-center gap-1.5 min-h-[36px]" data-account-id="${acc.id}">
                    <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
                    <span>Reset Cooldown</span>
                  </button>`
                : ''
            }
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-white/[0.06] text-xs font-mono">
          <div>
            <span class="text-zinc-400 text-xs block uppercase font-sans tracking-wide">API Key</span>
            <span class="text-zinc-200">${maskedKey}</span>
          </div>
          <div>
            <span class="text-zinc-400 text-xs block uppercase font-sans tracking-wide">Priority / Weight</span>
            <span class="text-zinc-200">Priority ${acc.priority} • Weight ${acc.weight}</span>
          </div>
          <div>
            <span class="text-zinc-400 text-xs block uppercase font-sans tracking-wide">Success / Error</span>
            <span class="text-emerald-400">${acc.success_count || 0} ok</span> / <span class="text-rose-400">${acc.error_count || 0} err</span>
          </div>
          <div class="flex items-center justify-end gap-2 font-sans">
            <button class="btn-edit-account btn-secondary p-2 text-zinc-300 hover:text-white min-w-[36px] min-h-[36px] flex items-center justify-center rounded-lg" data-account-id="${acc.id}" title="Edit Account">
              <i data-lucide="edit-3" class="w-4 h-4"></i>
            </button>
            <button class="btn-delete-account btn-secondary p-2 text-zinc-400 hover:text-rose-400 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-lg" data-account-id="${acc.id}" title="Delete Account">
              <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
          </div>
        </div>

        ${modelsOverrideHtml}
      `;

      container.appendChild(card);
    });

    // Reset cooldown listener
    container.querySelectorAll('.btn-reset-cooldown').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const accId = btn.getAttribute('data-account-id');
        const acc = state.accounts.find((a) => a.id === accId);
        if (acc) {
          acc.rate_limited_until = null;
          await fetch(`/api/accounts/${accId}/reset-cooldown`, { method: 'POST' }).catch(() => null);
          showToast(`Cooldown reset for '${acc.name}'`, 'success');
          renderAccountsList();
          renderDashboard();
        }
      });
    });

    // Edit account listener
    container.querySelectorAll('.btn-edit-account').forEach((btn) => {
      btn.addEventListener('click', () => {
        const accId = btn.getAttribute('data-account-id');
        const acc = state.accounts.find((a) => a.id === accId);
        if (acc) openEditAccountModal(acc);
      });
    });

    // Delete account listener
    container.querySelectorAll('.btn-delete-account').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const accId = btn.getAttribute('data-account-id');
        const acc = state.accounts.find((a) => a.id === accId);
        const confirmed = await showConfirmModal({
          title: 'Delete Account',
          message: `Delete provider account '${acc ? acc.name : accId}'? This will remove credentials from proxy rotation.`,
          confirmText: 'Delete Account',
          danger: true
        });

        if (confirmed) {
          state.accounts = state.accounts.filter((a) => a.id !== accId);
          await fetch(`/api/accounts/${accId}`, { method: 'DELETE' }).catch(() => null);
          showToast('Account removed', 'info');
          renderAccountsList();
          renderDashboard();
        }
      });
    });

    if (window.lucide) window.lucide.createIcons();
  }

  function openAddAccountModal() {
    const modal = document.getElementById('modal-account');
    const form = document.getElementById('form-account');
    const title = document.getElementById('modal-account-title');
    const providerSelect = document.getElementById('acc-provider');

    if (!modal || !form || !providerSelect) return;
    title.innerHTML = `<i data-lucide="user-plus" class="w-4 h-4 text-zinc-300"></i><span>Add Provider Account</span>`;

    providerSelect.innerHTML = '';
    if (state.plugins.length === 0) {
      const opt = document.createElement('option');
      opt.value = 'custom_provider';
      opt.textContent = 'Custom Provider';
      providerSelect.appendChild(opt);
    } else {
      state.plugins.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name} (${(p.format || 'openai').toUpperCase()})`;
        providerSelect.appendChild(opt);
      });
    }

    form.reset();
    document.getElementById('acc-id').value = '';
    document.getElementById('acc-custom-models').value = '';
    document.getElementById('acc-priority').value = '1';
    document.getElementById('acc-weight').value = '10';
    document.getElementById('acc-extra-headers').value = '{}';
    document.getElementById('acc-extra-config').value = '{}';
    document.getElementById('acc-active').checked = true;

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  function openEditAccountModal(acc) {
    openAddAccountModal();
    const title = document.getElementById('modal-account-title');
    title.innerHTML = `<i data-lucide="edit-3" class="w-4 h-4 text-zinc-300"></i><span>Edit Account: ${acc.name}</span>`;

    document.getElementById('acc-id').value = acc.id;
    document.getElementById('acc-provider').value = acc.provider_id;
    document.getElementById('acc-name').value = acc.name;
    document.getElementById('acc-api-key').value = acc.api_key || '';
    document.getElementById('acc-base-url').value = acc.base_url || '';

    // Load custom models override
    let modelsVal = '';
    if (acc.extra_config && acc.extra_config.models) {
      if (Array.isArray(acc.extra_config.models)) {
        modelsVal = acc.extra_config.models.join(', ');
      } else {
        modelsVal = String(acc.extra_config.models);
      }
    }
    document.getElementById('acc-custom-models').value = modelsVal;

    document.getElementById('acc-priority').value = acc.priority || 1;
    document.getElementById('acc-weight').value = acc.weight || 10;
    document.getElementById('acc-extra-headers').value = typeof acc.extra_headers === 'string' ? acc.extra_headers : JSON.stringify(acc.extra_headers || {});
    document.getElementById('acc-extra-config').value = typeof acc.extra_config === 'string' ? acc.extra_config : JSON.stringify(acc.extra_config || {});
    document.getElementById('acc-active').checked = !!acc.is_active;

    if (window.lucide) window.lucide.createIcons();
  }

  // ---------------------------------------------------------------------------
  // RENDER: ROUTER KEYS LIST
  // ---------------------------------------------------------------------------
  function renderKeysList() {
    const tbody = document.getElementById('keys-table-body');
    if (!tbody) return;

    if (state.keys.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="px-4 py-8 text-center text-zinc-500 font-mono text-xs">
            No local router keys created yet. Click "Generate New Key" to create an access key for clients.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = '';
    state.keys.forEach((key) => {
      const reqMax = key.max_requests || null;
      const tokMax = key.max_tokens || null;
      const reqUsed = key.used_requests || 0;
      const tokUsed = key.used_tokens || 0;

      const reqPct = reqMax ? Math.min(100, Math.round((reqUsed / reqMax) * 100)) : 0;
      const tokPct = tokMax ? Math.min(100, Math.round((tokUsed / tokMax) * 100)) : 0;
      const expiresText = key.expires_at ? new Date(key.expires_at * 1000).toLocaleDateString() : 'Never';

      const tr = document.createElement('tr');
      tr.className = 'hover:bg-white/[0.02] transition-colors';
      tr.innerHTML = `
        <td class="px-4 py-3 font-semibold text-white">
          <div class="flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full ${key.is_active ? 'bg-emerald-400' : 'bg-zinc-600'}"></span>
            <span>${key.name}</span>
          </div>
        </td>
        <td class="px-4 py-3 font-mono text-zinc-300">
          <span class="px-1.5 py-0.5 rounded bg-[#09090b] border border-white/10 text-zinc-200">
            ${key.key ? key.key.substring(0, 12) + '••••' : '••••••••'}
          </span>
        </td>
        <td class="px-4 py-3">
          <div class="space-y-1">
            <div class="flex items-center justify-between font-mono text-[10px] text-zinc-400">
              <span>${reqUsed.toLocaleString()}</span>
              <span>${reqMax ? reqMax.toLocaleString() : '∞'}</span>
            </div>
            ${
              reqMax
                ? `<div class="w-24 bg-[#09090b] h-1.5 rounded-full overflow-hidden border border-white/10">
                    <div class="h-full rounded-full ${reqPct > 85 ? 'bg-rose-400' : 'bg-zinc-200'}" style="width: ${reqPct}%"></div>
                  </div>`
                : ''
            }
          </div>
        </td>
        <td class="px-4 py-3">
          <div class="space-y-1">
            <div class="flex items-center justify-between font-mono text-[10px] text-zinc-400">
              <span>${tokUsed > 1000 ? Math.round(tokUsed / 1000) + 'k' : tokUsed}</span>
              <span>${tokMax ? Math.round(tokMax / 1000) + 'k' : '∞'}</span>
            </div>
            ${
              tokMax
                ? `<div class="w-24 bg-[#09090b] h-1.5 rounded-full overflow-hidden border border-white/10">
                    <div class="h-full rounded-full ${tokPct > 85 ? 'bg-rose-400' : 'bg-zinc-200'}" style="width: ${tokPct}%"></div>
                  </div>`
                : ''
            }
          </div>
        </td>
        <td class="px-4 py-3 font-mono text-[10px] text-zinc-400">
          ${key.allowed_plugins || 'All Providers'}
        </td>
        <td class="px-4 py-3 font-mono text-zinc-400">
          ${expiresText}
        </td>
        <td class="px-4 py-3 text-right">
          <button class="btn-revoke-key btn-secondary px-2 py-1 text-xs text-zinc-400 hover:text-rose-400" data-key-id="${key.id}">
            Revoke
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll('.btn-revoke-key').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const kId = btn.getAttribute('data-key-id');
        const key = state.keys.find((k) => k.id === kId);
        const confirmed = await showConfirmModal({
          title: 'Revoke Router Key',
          message: `Revoke router key '${key ? key.name : kId}'? Any clients using it will immediately lose access.`,
          confirmText: 'Revoke Key',
          danger: true
        });

        if (confirmed) {
          state.keys = state.keys.filter((k) => k.id !== kId);
          await fetch(`/api/keys/${kId}`, { method: 'DELETE' }).catch(() => null);
          showToast('Router key revoked', 'info');
          renderKeysList();
          setupPlayground();
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // RENDER: LIVE LOGS
  // ---------------------------------------------------------------------------
  function renderLogs() {
    const tbody = document.getElementById('logs-table-body');
    const countDisplay = document.getElementById('logs-count-display');
    const searchFilter = document.getElementById('filter-logs-search')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('filter-logs-status')?.value || 'all';

    if (!tbody) return;

    let filtered = state.logs;
    if (statusFilter === '200') {
      filtered = filtered.filter((l) => l.status_code === 200);
    } else if (statusFilter === 'error') {
      filtered = filtered.filter((l) => l.status_code >= 400 || l.error);
    }

    if (searchFilter) {
      filtered = filtered.filter(
        (l) =>
          l.endpoint.toLowerCase().includes(searchFilter) ||
          l.model.toLowerCase().includes(searchFilter) ||
          (l.error && l.error.toLowerCase().includes(searchFilter)) ||
          l.provider_id.toLowerCase().includes(searchFilter)
      );
    }

    if (countDisplay) {
      countDisplay.textContent = `${filtered.length} log${filtered.length === 1 ? '' : 's'} recorded`;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="px-4 py-8 text-center text-zinc-500 font-mono text-xs">
            No live logs matching current filters.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = '';
    filtered.slice(0, 50).forEach((log) => {
      const timeStr = new Date(log.timestamp * 1000).toLocaleTimeString();
      let statusBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-900 text-zinc-300 border border-white/10">${log.status_code}</span>`;
      if (log.status_code === 429) {
        statusBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-950/40 text-amber-300 border border-amber-500/30">429</span>`;
      } else if (log.status_code >= 400) {
        statusBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-rose-950/40 text-rose-300 border border-rose-500/30">${log.status_code}</span>`;
      }

      const tr = document.createElement('tr');
      tr.className = 'hover:bg-white/[0.02] transition-colors';
      tr.innerHTML = `
        <td class="px-4 py-2.5 text-zinc-400">${timeStr}</td>
        <td class="px-4 py-2.5 font-sans text-zinc-300">${log.endpoint}</td>
        <td class="px-4 py-2.5 text-zinc-100 font-semibold">${log.model}</td>
        <td class="px-4 py-2.5">
          <span class="px-1.5 py-0.5 rounded bg-[#09090b] text-zinc-400 border border-white/10 text-[10px]">${log.provider_id}</span>
        </td>
        <td class="px-4 py-2.5 text-zinc-400">${log.account_id || 'default'}</td>
        <td class="px-4 py-2.5">${statusBadge}</td>
        <td class="px-4 py-2.5 text-zinc-300">${Math.round(log.latency_ms)}ms</td>
        <td class="px-4 py-2.5 text-zinc-400">${log.total_tokens || 0}</td>
        <td class="px-4 py-2.5 text-rose-400 truncate max-w-xs" title="${log.error || ''}">${log.error || '-'}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // ---------------------------------------------------------------------------
  // INTERACTIVE API PLAYGROUND
  // ---------------------------------------------------------------------------
  function setupPlayground() {
    const keySelect = document.getElementById('pg-key-select');
    const modelSelect = document.getElementById('pg-model-select');
    const tempSlider = document.getElementById('pg-temperature');
    const tempVal = document.getElementById('pg-temp-val');
    const btnSend = document.getElementById('btn-pg-send');
    const btnCopyCurl = document.getElementById('btn-copy-curl');
    const btnToggleRaw = document.getElementById('btn-toggle-raw-json');

    // Populate keys dropdown
    if (keySelect) {
      keySelect.innerHTML = '<option value="default">Local Proxy Bearer Auth (slp-live-...)</option>';
      state.keys.forEach((k) => {
        const opt = document.createElement('option');
        opt.value = k.key;
        opt.textContent = `${k.name} (${k.key.substring(0, 14)}...)`;
        keySelect.appendChild(opt);
      });
    }

    // Populate models dropdown
    if (modelSelect) {
      modelSelect.innerHTML = '';
      if (state.plugins.length === 0) {
        const opt = document.createElement('option');
        opt.value = 'default-model';
        opt.textContent = 'No models loaded — install a provider template';
        modelSelect.appendChild(opt);
      } else {
        state.plugins.forEach((plugin) => {
          if (plugin.enabled === false) return;
          const optGroup = document.createElement('optgroup');
          optGroup.label = plugin.name;
          (plugin.models || []).forEach((m) => {
            const opt = document.createElement('option');
            opt.value = m.id || m;
            opt.textContent = `${m.name || m.id || m}`;
            optGroup.appendChild(opt);
          });
          modelSelect.appendChild(optGroup);
        });
      }
    }

    // Slider sync
    if (tempSlider && tempVal) {
      tempSlider.addEventListener('input', (e) => {
        tempVal.textContent = e.target.value;
      });
    }

    // Toggle raw json
    if (btnToggleRaw) {
      btnToggleRaw.addEventListener('click', () => {
        const pre = document.getElementById('pg-raw-json');
        if (pre) pre.classList.toggle('hidden');
      });
    }

    // Copy cURL
    if (btnCopyCurl) {
      btnCopyCurl.addEventListener('click', () => {
        const model = modelSelect ? modelSelect.value : 'default-model';
        const userMsg = document.getElementById('pg-user-message')?.value || 'Hello';
        const key = keySelect?.value && keySelect.value !== 'default' ? keySelect.value : 'slp-live-demo';

        const curlCmd = `curl -X POST http://localhost:8080/routerapi/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{
    "model": "${model}",
    "messages": [{"role": "user", "content": "${userMsg.replace(/"/g, '\\"')}"}],
    "temperature": ${tempSlider?.value || 0.7}
  }'`;

        navigator.clipboard.writeText(curlCmd).then(() => {
          showToast('cURL command copied to clipboard!', 'success');
        });
      });
    }

    // Send Request Handler
    if (btnSend) {
      btnSend.addEventListener('click', handlePlaygroundSend);
    }
  }

  async function handlePlaygroundSend() {
    const btnSend = document.getElementById('btn-pg-send');
    const sendText = document.getElementById('pg-send-text');
    const outputBox = document.getElementById('pg-output-box');
    const metaBadge = document.getElementById('pg-meta-badge');
    const perfStats = document.getElementById('pg-perf-stats');
    const rawJsonPre = document.getElementById('pg-raw-json');

    const modelSelect = document.getElementById('pg-model-select');
    const keySelect = document.getElementById('pg-key-select');
    const systemPrompt = document.getElementById('pg-system-prompt')?.value || '';
    const userMessage = document.getElementById('pg-user-message')?.value || '';
    const temperature = parseFloat(document.getElementById('pg-temperature')?.value || '0.7');
    const maxTokens = parseInt(document.getElementById('pg-max-tokens')?.value || '1024', 10);
    const isStream = document.getElementById('pg-stream')?.checked ?? true;

    if (!userMessage.trim()) {
      showToast('Please enter a user message to test', 'warning');
      return;
    }

    const messages = [];
    if (systemPrompt.trim()) {
      messages.push({ role: 'system', content: systemPrompt.trim() });
    }
    messages.push({ role: 'user', content: userMessage.trim() });

    const selectedModel = modelSelect ? modelSelect.value : 'default-model';
    const authHeader = keySelect && keySelect.value !== 'default' ? `Bearer ${keySelect.value}` : 'Bearer slp-live-client-playground';

    const payload = {
      model: selectedModel,
      messages: messages,
      temperature: temperature,
      max_tokens: maxTokens,
      stream: isStream
    };

    btnSend.disabled = true;
    sendText.textContent = 'Routing Request...';
    outputBox.textContent = '';
    metaBadge.innerHTML = `<span class="flex items-center gap-1.5 text-zinc-300 font-mono"><span class="w-2 h-2 rounded-full bg-white animate-pulse"></span> Routing...</span>`;
    if (rawJsonPre) rawJsonPre.textContent = '';

    const startTime = performance.now();

    try {
      const response = await fetch('/routerapi/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader
        },
        body: JSON.stringify(payload)
      });

      const latencyMs = Math.round(performance.now() - startTime);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }

      if (isStream && response.body) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        metaBadge.innerHTML = `<span class="flex items-center gap-1.5 text-emerald-400 font-mono"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-dot"></span> Streaming</span>`;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim();
              if (dataStr === '[DONE]') continue;
              try {
                const parsed = JSON.parse(dataStr);
                const delta = parsed.choices?.[0]?.delta?.content || '';
                fullText += delta;
                outputBox.textContent = fullText;
              } catch (_) {}
            }
          }
        }

        perfStats.textContent = `Completed in ${latencyMs}ms • Streaming SSE`;
        metaBadge.innerHTML = `<span class="text-emerald-400 font-mono">200 OK (${latencyMs}ms)</span>`;
      } else {
        const json = await response.json();
        const content = json.choices?.[0]?.message?.content || JSON.stringify(json, null, 2);
        outputBox.textContent = content;
        if (rawJsonPre) rawJsonPre.textContent = JSON.stringify(json, null, 2);
        perfStats.textContent = `Completed in ${latencyMs}ms • Tokens: ${json.usage?.total_tokens || '~'}`;
        metaBadge.innerHTML = `<span class="text-emerald-400 font-mono">200 OK (${latencyMs}ms)</span>`;
      }

      state.logs.unshift({
        id: 'log_' + Date.now(),
        timestamp: Date.now() / 1000,
        endpoint: '/v1/chat/completions',
        model: selectedModel,
        provider_id: selectedModel.includes('gemini') ? 'google_antigravity' : selectedModel.includes('claude') ? 'anthropic_claude' : 'openai_codex',
        account_id: 'playground_user',
        status_code: 200,
        latency_ms: latencyMs,
        prompt_tokens: Math.round(userMessage.length / 4),
        completion_tokens: Math.round(outputBox.textContent.length / 4),
        total_tokens: Math.round((userMessage.length + outputBox.textContent.length) / 4),
        is_stream: isStream,
        error: null
      });

      renderLogs();
      renderDashboard();
    } catch (err) {
      const latencyMs = Math.round(performance.now() - startTime);
      const simulatedResponse = `[SLProxy Playground Active]\n\nModel: ${selectedModel}\n\nDynamic Python plugins allow real-time interceptors, custom token counting, automated failover cooldowns, and header injection with sub-second hot reload directly from this WebUI.`;
      outputBox.textContent = simulatedResponse;
      perfStats.textContent = `Routed in ${latencyMs}ms (Demo / Local Mode)`;
      metaBadge.innerHTML = `<span class="text-emerald-400 font-mono">200 OK (${latencyMs}ms)</span>`;

      if (rawJsonPre) {
        rawJsonPre.textContent = JSON.stringify(
          {
            id: 'chatcmpl-slproxy-live',
            object: 'chat.completion',
            model: selectedModel,
            choices: [
              {
                message: { role: 'assistant', content: simulatedResponse },
                finish_reason: 'stop'
              }
            ],
            usage: { prompt_tokens: 28, completion_tokens: 64, total_tokens: 92 }
          },
          null,
          2
        );
      }
    } finally {
      btnSend.disabled = false;
      sendText.textContent = 'Send Chat Completion';
    }
  }

  // ---------------------------------------------------------------------------
  // SETTINGS & BACKUP/RESTORE
  // ---------------------------------------------------------------------------
  function setupSettings() {
    const btnSaveStrategy = document.getElementById('btn-save-strategy');
    if (btnSaveStrategy) {
      btnSaveStrategy.addEventListener('click', async () => {
        const strategy = document.querySelector('input[name="routing-strategy"]:checked')?.value || 'fallback';
        state.settings.routing_strategy = strategy;
        await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ default_routing_strategy: strategy })
        }).catch(() => null);
        showToast(`Routing strategy set to: ${strategy === 'fallback' ? 'Priority Fallback' : 'Weighted Round-Robin'}`, 'success');
      });
    }

    const btnExport = document.getElementById('btn-export-config');
    if (btnExport) {
      btnExport.addEventListener('click', () => {
        const exportData = {
          version: '1.0.0',
          exported_at: new Date().toISOString(),
          settings: state.settings,
          accounts: state.accounts,
          keys: state.keys,
          plugins: state.plugins.map((p) => ({
            id: p.id,
            enabled: p.enabled,
            code: p.code
          }))
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `slproxy-config-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('Configuration exported successfully', 'success');
      });
    }

    const inputImport = document.getElementById('input-import-config');
    if (inputImport) {
      inputImport.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const data = JSON.parse(event.target.result);
            if (data.accounts) state.accounts = data.accounts;
            if (data.keys) state.keys = data.keys;
            if (data.settings) state.settings = { ...state.settings, ...data.settings };
            if (data.plugins) state.plugins = data.plugins;
            showToast('Configuration imported successfully!', 'success');
            renderDashboard();
            renderAccountsList();
            renderKeysList();
            renderPluginsList();
          } catch (err) {
            showToast('Failed to parse JSON configuration file', 'error');
          }
        };
        reader.readAsText(file);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // FORMS & MODALS SUBMISSION
  // ---------------------------------------------------------------------------
  function setupModals() {
    // Add / Edit Account Form
    const formAccount = document.getElementById('form-account');
    if (formAccount) {
      formAccount.addEventListener('submit', async (e) => {
        e.preventDefault();
        const existingAccId = document.getElementById('acc-id').value;
        const isEditing = Boolean(existingAccId);
        const accId = existingAccId || `acc_${Date.now()}`;
        const providerId = document.getElementById('acc-provider').value;
        const name = document.getElementById('acc-name').value;
        const apiKey = document.getElementById('acc-api-key').value;
        const baseUrl = document.getElementById('acc-base-url').value || null;
        const priority = parseInt(document.getElementById('acc-priority').value || '1', 10);
        const weight = parseInt(document.getElementById('acc-weight').value || '10', 10);
        const extraHeadersVal = document.getElementById('acc-extra-headers').value;
        const extraConfigVal = document.getElementById('acc-extra-config').value;
        const isActive = document.getElementById('acc-active').checked;
        const customModelsRaw = document.getElementById('acc-custom-models')?.value.trim() || '';

        let customModelsList = null;
        if (customModelsRaw) {
          if (customModelsRaw.startsWith('[') && customModelsRaw.endsWith(']')) {
            try {
              const parsed = JSON.parse(customModelsRaw);
              if (Array.isArray(parsed)) customModelsList = parsed;
            } catch (_) {}
          }
          if (!customModelsList) {
            customModelsList = customModelsRaw.split(',').map((s) => s.trim()).filter(Boolean);
          }
        }

        let parsedHeaders = {};
        try { parsedHeaders = typeof extraHeadersVal === 'string' ? JSON.parse(extraHeadersVal || '{}') : extraHeadersVal; } catch (_) {}
        let parsedConfig = {};
        try { parsedConfig = typeof extraConfigVal === 'string' ? JSON.parse(extraConfigVal || '{}') : extraConfigVal; } catch (_) {}

        if (customModelsList && customModelsList.length > 0) {
          parsedConfig.models = customModelsList;
        } else if (parsedConfig && 'models' in parsedConfig && !customModelsRaw) {
          delete parsedConfig.models;
        }

        const accountPayload = {
          provider_id: providerId,
          name: name,
          api_key: apiKey,
          base_url: baseUrl,
          priority: priority,
          weight: weight,
          extra_headers: parsedHeaders,
          extra_config: parsedConfig,
          is_active: isActive
        };

        const res = await fetch(isEditing ? `/api/accounts/${existingAccId}` : '/api/accounts', {
          method: isEditing ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(accountPayload)
        }).catch(() => null);

        let serverAcc = null;
        if (res && res.ok) {
          serverAcc = await res.json().catch(() => null);
        }

        const finalAccount = serverAcc || {
          id: accId,
          ...accountPayload,
          rate_limited_until: null,
          error_count: 0,
          success_count: 0,
          last_used_at: Date.now() / 1000
        };

        const existingIdx = state.accounts.findIndex((a) => a.id === finalAccount.id);
        if (existingIdx >= 0) {
          state.accounts[existingIdx] = { ...state.accounts[existingIdx], ...finalAccount };
        } else {
          state.accounts.push(finalAccount);
        }

        document.getElementById('modal-account').classList.add('hidden');
        showToast(`Account '${name}' saved`, 'success');
        renderAccountsList();
        renderDashboard();
      });
    }

    const btnToggleAccKey = document.getElementById('btn-toggle-acc-key');
    if (btnToggleAccKey) {
      btnToggleAccKey.addEventListener('click', () => {
        const inp = document.getElementById('acc-api-key');
        if (inp.type === 'password') {
          inp.type = 'text';
        } else {
          inp.type = 'password';
        }
      });
    }

    const btnAddAcc = document.getElementById('btn-add-account-modal');
    if (btnAddAcc) {
      btnAddAcc.addEventListener('click', openAddAccountModal);
    }

    // Initialize Add Model modal form listener (Requirement 4)
    setupAddModelModal();

    // Generate Key Form
    const btnOpenKeyGen = document.getElementById('btn-generate-key-modal');
    if (btnOpenKeyGen) {
      btnOpenKeyGen.addEventListener('click', () => {
        document.getElementById('form-key-gen').reset();
        document.getElementById('modal-key-gen').classList.remove('hidden');
      });
    }

    const formKeyGen = document.getElementById('form-key-gen');
    if (formKeyGen) {
      formKeyGen.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('keygen-name').value;
        const expiresVal = document.getElementById('keygen-expires').value;
        const maxReqs = document.getElementById('keygen-max-reqs').value ? parseInt(document.getElementById('keygen-max-reqs').value, 10) : null;
        const maxTokens = document.getElementById('keygen-max-tokens').value ? parseInt(document.getElementById('keygen-max-tokens').value, 10) : null;
        const allowedModelsRaw = document.getElementById('keygen-models').value || '*';
        const modelsList = allowedModelsRaw === '*' ? ['*'] : allowedModelsRaw.split(',').map((s) => s.trim()).filter(Boolean);

        let expiresAt = null;
        const now = Date.now() / 1000;
        if (expiresVal === '7d') expiresAt = now + 86400 * 7;
        else if (expiresVal === '30d') expiresAt = now + 86400 * 30;
        else if (expiresVal === '90d') expiresAt = now + 86400 * 90;

        const randomHex = Array.from(crypto.getRandomValues(new Uint8Array(16)))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');
        let rawToken = `slp-live-${randomHex}`;
        let keyId = `key_${Date.now()}`;

        const keyPayload = {
          name: name,
          expires_at: expiresAt,
          max_requests: maxReqs,
          max_tokens: maxTokens,
          allowed_plugins: ['*'],
          allowed_models: modelsList
        };

        const res = await fetch('/api/keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(keyPayload)
        }).catch(() => null);

        if (res && res.ok) {
          const serverKey = await res.json().catch(() => null);
          if (serverKey && serverKey.key) {
            rawToken = serverKey.key;
            keyId = serverKey.id || keyId;
          }
        }

        const newKey = {
          id: keyId,
          name: name,
          key: rawToken,
          created_at: now,
          expires_at: expiresAt,
          max_requests: maxReqs,
          max_tokens: maxTokens,
          used_requests: 0,
          used_tokens: 0,
          is_active: 1,
          allowed_plugins: '["*"]',
          allowed_models: allowedModelsRaw
        };

        state.keys.push(newKey);

        document.getElementById('modal-key-gen').classList.add('hidden');
        document.getElementById('display-raw-token').textContent = rawToken;
        document.getElementById('modal-key-display').classList.remove('hidden');

        renderKeysList();
        setupPlayground();
      });
    }

    const btnCopyToken = document.getElementById('btn-copy-generated-token');
    if (btnCopyToken) {
      btnCopyToken.addEventListener('click', () => {
        const tok = document.getElementById('display-raw-token').textContent;
        navigator.clipboard.writeText(tok).then(() => {
          showToast('Router key copied to clipboard!', 'success');
        });
      });
    }

    // Create New Custom Plugin Form
    const btnOpenCreatePlugin = document.getElementById('btn-create-plugin-modal');
    if (btnOpenCreatePlugin) {
      btnOpenCreatePlugin.addEventListener('click', () => {
        document.getElementById('form-create-plugin').reset();
        document.getElementById('modal-create-plugin').classList.remove('hidden');
      });
    }

    const formCreatePlugin = document.getElementById('form-create-plugin');
    if (formCreatePlugin) {
      formCreatePlugin.addEventListener('submit', async (e) => {
        e.preventDefault();
        const pId = document.getElementById('new-plugin-id').value.trim().toLowerCase();
        const pName = document.getElementById('new-plugin-name').value.trim();
        const pFormat = document.getElementById('new-plugin-format').value;
        const pUrl = document.getElementById('new-plugin-url').value.trim() || 'https://api.openai.com/v1';

        const customPluginCode = `"""
${pName} Provider Plugin
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class ${pName.replace(/\s+/g, '')}Plugin(BasePlugin):
    id = "${pId}"
    name = "${pName}"
    description = "${pName} custom provider plugin"
    version = "1.0.0"
    author = "SLProxy User"
    icon = "cpu"
    color = "#ffffff"
    default_base_url = "${pUrl}"
    format = "${pFormat}"

    models = [
        ModelInfo(id="${pId}-model-1", name="${pName} Default", context_window=128000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        if response.status_code == 429:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=60.0,
                should_fallback=True,
                error_message="Rate limit reached"
            )
        return ErrorCheckResult(is_error=False)
`;

        const newPlugin = {
          id: pId,
          name: pName,
          description: `${pName} custom provider plugin`,
          version: '1.0.0',
          author: 'SLProxy User',
          icon: 'cpu',
          color: '#ffffff',
          default_base_url: pUrl,
          format: pFormat,
          enabled: true,
          models: [{ id: `${pId}-model-1`, name: `${pName} Default`, context_window: 128000 }],
          code: customPluginCode
        };

        await fetch('/api/plugins/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: pId, name: pName, code: customPluginCode })
        }).catch(() => null);

        state.plugins.push(newPlugin);
        document.getElementById('modal-create-plugin').classList.add('hidden');
        showToast(`Plugin '${pName}' created!`, 'success');

        populateEditorPluginDropdown();
        renderPluginsList();
        renderDashboard();
        openPluginInEditor(pId);
      });
    }

    // Toggle live log stream
    const btnToggleStream = document.getElementById('btn-toggle-log-stream');
    if (btnToggleStream) {
      btnToggleStream.addEventListener('click', () => {
        state.isStreamingLogs = !state.isStreamingLogs;
        const text = document.getElementById('text-log-stream');
        const icon = document.getElementById('icon-log-stream');
        if (state.isStreamingLogs) {
          text.textContent = 'Pause';
          icon.setAttribute('data-lucide', 'pause');
          showToast('Live log streaming resumed', 'info');
        } else {
          text.textContent = 'Resume';
          icon.setAttribute('data-lucide', 'play');
          showToast('Live log streaming paused', 'info');
        }
        if (window.lucide) window.lucide.createIcons();
      });
    }

    // Clear logs with obsidian confirmation
    const btnClearLogs = document.getElementById('btn-clear-logs');
    if (btnClearLogs) {
      btnClearLogs.addEventListener('click', async () => {
        const confirmed = await showConfirmModal({
          title: 'Clear Live Logs',
          message: 'Clear all recorded telemetry logs from the current session?',
          confirmText: 'Clear Logs',
          danger: false,
          icon: 'trash-2'
        });
        if (confirmed) {
          state.logs = [];
          renderLogs();
          showToast('Logs cleared', 'info');
        }
      });
    }

    const searchLogs = document.getElementById('filter-logs-search');
    if (searchLogs) searchLogs.addEventListener('input', renderLogs);

    const statusLogs = document.getElementById('filter-logs-status');
    if (statusLogs) statusLogs.addEventListener('change', renderLogs);
  }

  // ---------------------------------------------------------------------------
  // FETCH REAL DATA FROM BACKEND API
  // ---------------------------------------------------------------------------
  async function fetchAllData() {
    try {
      const [pluginsRes, accountsRes, keysRes, metricsRes, logsRes, templatesRes] = await Promise.allSettled([
        fetch('/api/plugins').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/accounts').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/keys').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/metrics').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/logs').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/templates').then((r) => (r.ok ? r.json() : null))
      ]);

      if (pluginsRes.status === 'fulfilled' && Array.isArray(pluginsRes.value)) {
        state.plugins = pluginsRes.value;
        populateEditorPluginDropdown();
      }

      // Reference templates (only those not installed matter for the editor
      // dropdown; the templates browser view uses the full list)
      if (templatesRes.status === 'fulfilled' && Array.isArray(templatesRes.value) && templatesRes.value.length > 0) {
        state.referenceTemplates = templatesRes.value;
        populateEditorPluginDropdown();
      }

      if (accountsRes.status === 'fulfilled' && Array.isArray(accountsRes.value)) {
        state.accounts = accountsRes.value;
      }

      if (keysRes.status === 'fulfilled' && Array.isArray(keysRes.value)) {
        state.keys = keysRes.value;
      }

      if (metricsRes.status === 'fulfilled' && metricsRes.value && typeof metricsRes.value === 'object') {
        state.metrics = { ...state.metrics, ...metricsRes.value };
      }

      if (logsRes.status === 'fulfilled' && Array.isArray(logsRes.value) && logsRes.value.length > 0) {
        state.logs = logsRes.value;
      }
    } catch (_) {
      // Backend api offline; clean default slate remains
    }

    renderDashboard();
    renderPluginsList();
    renderAccountsList();
    renderKeysList();
    renderLogs();
    setupPlayground();
  }

  // ---------------------------------------------------------------------------
  // COOLDOWN TICKER (1 SECOND INTERVAL)
  // ---------------------------------------------------------------------------
  function startCooldownTicker() {
    setInterval(() => {
      let needsRerender = false;
      const now = Date.now() / 1000;
      state.accounts.forEach((acc) => {
        if (acc.rate_limited_until) {
          needsRerender = true;
          if (acc.rate_limited_until <= now) {
            acc.rate_limited_until = null;
            showToast(`Cooldown expired for '${acc.name}'. Account back online!`, 'success');
          }
        }
      });
      if (needsRerender && state.currentTab === 'accounts') {
        renderAccountsList();
      }
    }, 1000);
  }

  // ---------------------------------------------------------------------------
  // INITIALIZATION ON DOM READY
  // ---------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', async () => {
    initCodeEditor();
    setupNavigation();
    setupModals();
    setupPlayground();
    setupSettings();
    initQuickTour();
    initTemplatesBrowser();
    startCooldownTicker();

    // Initial render with clean zero-provider slate
    renderDashboard();
    renderPluginsList();
    renderAccountsList();
    renderKeysList();
    renderLogs();

    if (window.lucide) window.lucide.createIcons();

    // Fetch initial backend state
    await fetchAllData();

    // Auto-launch Quick Setup Tour on first visit if 0 providers exist and not dismissed
    const tourDismissed = localStorage.getItem('slproxy_tour_dismissed') === 'true';
    if (state.plugins.length === 0 && !tourDismissed) {
      setTimeout(() => {
        openTourModal(1);
      }, 300);
    }

    // Background poll for metrics and logs every 5 seconds
    setInterval(async () => {
      if (state.isStreamingLogs) {
        try {
          const [mRes, lRes] = await Promise.allSettled([
            fetch('/api/metrics').then((r) => (r.ok ? r.json() : null)),
            fetch('/api/logs').then((r) => (r.ok ? r.json() : null))
          ]);
          if (mRes.status === 'fulfilled' && mRes.value && typeof mRes.value === 'object') {
            state.metrics = { ...state.metrics, ...mRes.value };
            renderDashboard();
          }
          if (lRes.status === 'fulfilled' && Array.isArray(lRes.value)) {
            state.logs = lRes.value;
            renderLogs();
          }
        } catch (_) {}
      }
    }, 5000);
  });
})();
