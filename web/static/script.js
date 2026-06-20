document.addEventListener('DOMContentLoaded', async () => {
    // Set default date to today
    const dateInput = document.getElementById('analysis_date');
    if(dateInput) {
        const today = new Date().toISOString().split('T')[0];
        dateInput.value = today;
    }

    let modelOptionsCache = {};
    let progressInterval = null;
    let lastRawMarkdown = "";
    
    // Fetch options from backend
    try {
        const res = await fetch('/api/options');
        const data = await res.json();
        if (data.models) {
            modelOptionsCache = data.models;
        }
    } catch (e) {
        console.error("Failed to fetch model options", e);
    }

    const form = document.getElementById('config-form');
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Get form data
        const formData = new FormData(form);
        
        // Extract selected analysts
        const analysts = [];
        document.querySelectorAll('input[name="analysts"]:checked').forEach(checkbox => {
            analysts.push(checkbox.value);
        });

        if (analysts.length === 0) {
            alert("Please select at least one analyst.");
            return;
        }

        let selectedTicker = formData.get('ticker_select');
        if (selectedTicker === 'custom') {
            selectedTicker = formData.get('ticker_custom');
            if (!selectedTicker) {
                alert("Please enter a custom ticker.");
                return;
            }
        }
        
        let assetType = formData.get('asset_type');
        const tickerUpper = selectedTicker.toUpperCase();
        if (tickerUpper.endsWith('-USD') || tickerUpper.endsWith('-USDT') || tickerUpper.endsWith('-BTC') || tickerUpper.endsWith('-ETH')) {
            assetType = 'crypto';
        } else {
            assetType = 'stock';
        }

        let outputLanguage = formData.get('output_language_select');
        if (outputLanguage === 'custom') {
            outputLanguage = formData.get('output_language_custom');
            if (!outputLanguage) {
                alert("Please enter a custom language.");
                return;
            }
        }

        const payload = {
            ticker: selectedTicker,
            asset_type: assetType,
            analysis_date: formData.get('analysis_date'),
            analysts: analysts,
            llm_provider: formData.get('llm_provider'),
            trading_mode: formData.get('trading_mode'),
            timeframe: formData.get('timeframe'),
            output_language: outputLanguage,
            research_depth: parseInt(formData.get('research_depth')),
            report_length: formData.get('report_length'),
            shallow_thinker: formData.get('shallow_thinker'),
            deep_thinker: formData.get('deep_thinker'),
            api_key: formData.get('api_key') || null
        };

        // Get UI elements
        const btn = document.getElementById('run-btn');
        const btnText = btn.querySelector('.btn-text');
        const loader = btn.querySelector('.loader');
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');

        // Switch to loading state
        showState('loading-state');
        btn.disabled = true;
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');

        // Progress logic
        const depth = parseInt(formData.get('research_depth')) || 2;
        const totalSeconds = depth * 60;
        let elapsed = 0;
        
        if (progressBar && progressText) {
            progressBar.style.width = '0%';
            progressText.innerText = `Estimated time remaining: ${totalSeconds} seconds`;
            
            progressInterval = setInterval(() => {
                elapsed++;
                if (elapsed < totalSeconds) {
                    const percent = Math.min(99, (elapsed / totalSeconds) * 100);
                    progressBar.style.width = `${percent}%`;
                    progressText.innerText = `Estimated time remaining: ${totalSeconds - elapsed} seconds`;
                } else {
                    progressBar.style.width = '99%';
                    progressText.innerText = `Finalizing... almost done!`;
                }
            }, 1000);
        }

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            
            clearInterval(progressInterval);
            progressBar.style.width = '100%';
            progressText.innerText = 'Complete!';

            if (data.status === 'success') {
                lastRawMarkdown = data.report_markdown;
                renderReport(payload.ticker, data.decision, data.report_markdown);
                showState('result-state');
            } else {
                showError(data.message, data.traceback);
            }
        } catch (error) {
            if (progressInterval) clearInterval(progressInterval);
            showError("Network Error", error.toString());
        } finally {
            if (btn && btnText && loader) {
                btn.disabled = false;
                btnText.classList.remove('hidden');
                loader.classList.add('hidden');
            }
        }
    });

    // Handle provider changes to update default models
    const providerSelect = document.getElementById('llm_provider');
    const shallowSelect = document.getElementById('shallow_thinker');
    const deepSelect = document.getElementById('deep_thinker');
    const downloadBtn = document.getElementById('download-btn');

    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            if (!lastRawMarkdown) return;
            const blob = new Blob([lastRawMarkdown], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Analysis_Report.md`;
            a.click();
            URL.revokeObjectURL(url);
        });
    }

    function updateModelDropdowns() {
        const provider = providerSelect.value;
        const options = modelOptionsCache[provider] || { quick: [], deep: [] };
        
        // Populate quick
        shallowSelect.innerHTML = '';
        options.quick.forEach(opt => {
            const optionEl = document.createElement('option');
            optionEl.text = opt[0];
            optionEl.value = opt[1];
            shallowSelect.add(optionEl);
        });

        // Populate deep
        deepSelect.innerHTML = '';
        options.deep.forEach(opt => {
            const optionEl = document.createElement('option');
            optionEl.text = opt[0];
            optionEl.value = opt[1];
            deepSelect.add(optionEl);
        });
    }

    providerSelect.addEventListener('change', updateModelDropdowns);

    // Initial population
    if (Object.keys(modelOptionsCache).length > 0) {
        updateModelDropdowns();
    }

    // Custom ticker handling
    const tickerSelect = document.getElementById('ticker_select');
    const tickerCustom = document.getElementById('ticker_custom');
    const fundamentalsContainer = document.getElementById('fundamentals-container');
    const fundamentalsCheckbox = document.getElementById('analyst_fundamentals');
    
    function checkCryptoAndHideFundamentals() {
        let selectedTicker = tickerSelect.value;
        if (selectedTicker === 'custom') {
            selectedTicker = tickerCustom.value;
        }
        
        const tickerUpper = (selectedTicker || "").toUpperCase();
        const isCrypto = tickerUpper.endsWith('-USD') || tickerUpper.endsWith('-USDT') || tickerUpper.endsWith('-BTC') || tickerUpper.endsWith('-ETH');
        
        if (isCrypto) {
            fundamentalsContainer.classList.add('hidden');
            fundamentalsCheckbox.checked = false;
        } else {
            fundamentalsContainer.classList.remove('hidden');
            // We don't auto-check it, we just let the user see it
        }
    }

    tickerSelect.addEventListener('change', (e) => {
        if (e.target.value === 'custom') {
            tickerCustom.classList.remove('hidden');
            tickerCustom.required = true;
        } else {
            tickerCustom.classList.add('hidden');
            tickerCustom.required = false;
        }
        checkCryptoAndHideFundamentals();
    });

    tickerCustom.addEventListener('input', checkCryptoAndHideFundamentals);

    // Custom Language handling
    const languageSelect = document.getElementById('output_language_select');
    const languageCustom = document.getElementById('output_language_custom');
    
    languageSelect.addEventListener('change', (e) => {
        if (e.target.value === 'custom') {
            languageCustom.classList.remove('hidden');
            languageCustom.required = true;
        } else {
            languageCustom.classList.add('hidden');
            languageCustom.required = false;
        }
    });

    // Run once on load
    checkCryptoAndHideFundamentals();
});

function showState(stateId) {
    document.querySelectorAll('.state-view').forEach(el => {
        el.classList.remove('active');
        el.classList.add('hidden');
    });
    
    const target = document.getElementById(stateId);
    if(target) {
        target.classList.remove('hidden');
        target.classList.add('active');
        
        // Auto-scroll to content on mobile (except for welcome screen)
        if (window.innerWidth <= 768 && stateId !== 'welcome-state') {
            setTimeout(() => {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);
        }
    }
}

function setButtonLoading(isLoading) {
    const btn = document.getElementById('run-btn');
    const text = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.loader');
    
    if (isLoading) {
        btn.disabled = true;
        text.classList.add('hidden');
        loader.classList.remove('hidden');
    } else {
        btn.disabled = false;
        text.classList.remove('hidden');
        loader.classList.add('hidden');
    }
}

function renderReport(ticker, decision, markdown) {
    document.getElementById('report-ticker').textContent = ticker.toUpperCase();
    
    const badge = document.getElementById('report-decision');
    badge.textContent = decision;
    badge.className = 'decision-badge'; // reset
    
    const decLower = (decision || "").toLowerCase();
    if (decLower.includes('bullish') || decLower.includes('long') || decLower.includes('buy')) {
        badge.classList.add('bullish');
    } else if (decLower.includes('bearish') || decLower.includes('short') || decLower.includes('sell')) {
        badge.classList.add('bearish');
    } else {
        badge.classList.add('neutral');
    }

    // Configure marked options if needed
    marked.setOptions({
        gfm: true,
        breaks: true
    });

    document.getElementById('report-content').innerHTML = marked.parse(markdown);
}

function showError(message, traceback) {
    document.getElementById('error-message').textContent = message;
    document.getElementById('error-traceback').textContent = traceback || "No traceback available.";
    showState('error-state');
}

function resetView() {
    showState('welcome-state');
}
