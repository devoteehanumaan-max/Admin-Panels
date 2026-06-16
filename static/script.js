// User Dashboard Script — UX Overhaul
document.addEventListener('DOMContentLoaded', function() {

    // ============================================
    // CUSTOM DIALOG SYSTEM (replaces alert/confirm/prompt)
    // ============================================

    const dialogHtml = `
        <div id="custom-dialog-overlay">
            <div id="custom-dialog">
                <div id="custom-dialog-header">
                    <span id="custom-dialog-icon-el"></span>
                    <h3 id="custom-dialog-title-el"></h3>
                </div>
                <p id="custom-dialog-message-el"></p>
                <input id="custom-dialog-input-el" class="custom-dialog-input" type="text" placeholder="">
                <div id="custom-dialog-buttons-el">
                    <button id="custom-dialog-cancel-el" class="custom-dialog-btn cancel"></button>
                    <button id="custom-dialog-ok-el" class="custom-dialog-btn ok"></button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', dialogHtml);

    const dialogOverlay  = document.getElementById('custom-dialog-overlay');
    const dialogTitle    = document.getElementById('custom-dialog-title-el');
    const dialogIcon     = document.getElementById('custom-dialog-icon-el');
    const dialogMessage  = document.getElementById('custom-dialog-message-el');
    const dialogInput    = document.getElementById('custom-dialog-input-el');
    const dialogCancelBtn= document.getElementById('custom-dialog-cancel-el');
    const dialogOkBtn    = document.getElementById('custom-dialog-ok-el');

    function openDialog()  { dialogOverlay.classList.add('active'); }
    function closeDialog() {
        dialogOverlay.classList.remove('active');
        setTimeout(() => { dialogInput.value = ''; }, 300);
    }

    function showAlert(message, type = 'info', title = null) {
        return new Promise(resolve => {
            const icons  = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
            const titles = { success: 'Success', error: 'Error', warning: 'Warning', info: 'Notice' };
            dialogIcon.textContent = icons[type] || icons.info;
            dialogTitle.textContent = title || titles[type] || 'Notice';
            dialogMessage.innerHTML = message;
            dialogInput.style.display = 'none';
            dialogCancelBtn.style.display = 'none';
            dialogOkBtn.textContent = 'OK';
            dialogOkBtn.className = `custom-dialog-btn ok ${type}`;
            openDialog();
            const onOk = () => { closeDialog(); dialogOkBtn.removeEventListener('click', onOk); resolve(); };
            dialogOkBtn.addEventListener('click', onOk);
        });
    }

    function showConfirm(message, title = 'Confirm', type = 'warning') {
        return new Promise(resolve => {
            const icons = { warning: '⚠️', danger: '🗑️', info: '❓' };
            dialogIcon.textContent = icons[type] || icons.warning;
            dialogTitle.textContent = title;
            dialogMessage.innerHTML = message;
            dialogInput.style.display = 'none';
            dialogCancelBtn.style.display = 'inline-flex';
            dialogCancelBtn.textContent = 'Cancel';
            dialogOkBtn.textContent = type === 'danger' ? 'Delete' : 'Confirm';
            dialogOkBtn.className = `custom-dialog-btn ok ${type === 'danger' ? 'danger' : ''}`;
            openDialog();
            const cleanup = () => {
                dialogOkBtn.removeEventListener('click', onOk);
                dialogCancelBtn.removeEventListener('click', onCancel);
            };
            const onOk     = () => { closeDialog(); cleanup(); resolve(true);  };
            const onCancel = () => { closeDialog(); cleanup(); resolve(false); };
            dialogOkBtn.addEventListener('click', onOk);
            dialogCancelBtn.addEventListener('click', onCancel);
        });
    }

    function showPrompt(message, defaultValue = '', title = 'Input Required', placeholder = '') {
        return new Promise(resolve => {
            dialogIcon.textContent = '✏️';
            dialogTitle.textContent = title;
            dialogMessage.innerHTML = message;
            dialogInput.style.display = 'block';
            dialogInput.value = defaultValue;
            dialogInput.placeholder = placeholder || 'Type here...';
            dialogCancelBtn.style.display = 'inline-flex';
            dialogCancelBtn.textContent = 'Cancel';
            dialogOkBtn.textContent = 'Submit';
            dialogOkBtn.className = 'custom-dialog-btn ok';
            openDialog();
            setTimeout(() => dialogInput.focus(), 100);
            const cleanup = () => {
                dialogOkBtn.removeEventListener('click', onOk);
                dialogCancelBtn.removeEventListener('click', onCancel);
                dialogInput.removeEventListener('keydown', onKey);
            };
            const onOk     = () => { const v = dialogInput.value; closeDialog(); cleanup(); resolve(v); };
            const onCancel = () => { closeDialog(); cleanup(); resolve(null); };
            const onKey    = (e) => { if (e.key === 'Enter') onOk(); if (e.key === 'Escape') onCancel(); };
            dialogOkBtn.addEventListener('click', onOk);
            dialogCancelBtn.addEventListener('click', onCancel);
            dialogInput.addEventListener('keydown', onKey);
        });
    }

    dialogOverlay.addEventListener('click', (e) => {
        if (e.target === dialogOverlay) closeDialog();
    });

    // ============================================
    // CLIPBOARD COPY
    // ============================================

    function copyToClipboard(text, toastMsg = '📋 Copied to clipboard!') {
        const doIt = () => {
            const el = document.createElement('textarea');
            el.value = text;
            Object.assign(el.style, { position: 'fixed', opacity: '0', top: '0', left: '0' });
            document.body.appendChild(el);
            el.select();
            try { document.execCommand('copy'); showToast(toastMsg, 'success', 2500); }
            catch { showToast('Copy failed — please copy manually', 'error'); }
            document.body.removeChild(el);
        };
        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(text)
                .then(() => showToast(toastMsg, 'success', 2500))
                .catch(doIt);
        } else { doIt(); }
    }

    // ============================================
    // TOAST NOTIFICATION SYSTEM
    // ============================================

    if (!document.getElementById('notification-container')) {
        const c = document.createElement('div');
        c.id = 'notification-container';
        document.body.appendChild(c);
    }

    function showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('notification-container');
        const icons = { success: 'fa-check-circle', error: 'fa-times-circle',
                        warning: 'fa-exclamation-triangle', info: 'fa-bell' };
        const colors = { success: 'var(--accent-green)', error: 'var(--accent-red)',
                         warning: 'var(--accent-yellow)', info: 'var(--accent-pink)' };
        const color = colors[type] || colors.info;
        const icon  = icons[type]  || icons.info;

        const toast = document.createElement('div');
        toast.className = `notification-toast toast-${type}`;
        toast.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;">
                <i class="fas ${icon}" style="color:${color};font-size:1.1rem;flex-shrink:0;"></i>
                <span style="flex:1;color:var(--text-primary);font-size:0.95rem;">${escapeHtml(message)}</span>
                <button class="close-toast" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:1.1rem;line-height:1;padding:2px 4px;">&times;</button>
            </div>`;
        container.appendChild(toast);

        const remove = () => {
            toast.style.animation = 'slideOutRight 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        };
        const timer = setTimeout(remove, duration);
        toast.querySelector('.close-toast').addEventListener('click', () => { clearTimeout(timer); remove(); });
    }

    function showNotificationToast(title, message, notifId) {
        const container = document.getElementById('notification-container');
        const toast = document.createElement('div');
        toast.className = 'notification-toast toast-notif';
        toast.setAttribute('data-id', notifId);
        toast.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;">
                <div style="background:var(--accent-pink);width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                    <i class="fas fa-bell" style="color:black;font-size:0.9rem;"></i>
                </div>
                <div style="flex:1;">
                    <strong style="color:var(--accent-pink);display:block;font-size:0.9rem;">${escapeHtml(title)}</strong>
                    <span style="color:var(--text-secondary);font-size:0.82rem;">${escapeHtml(message)}</span>
                </div>
                <button class="close-toast" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:1.2rem;">&times;</button>
            </div>`;
        container.appendChild(toast);
        const remove = () => { toast.style.animation = 'slideOutRight 0.3s ease forwards'; setTimeout(() => toast.remove(), 300); };
        const timer = setTimeout(remove, 8000);
        toast.addEventListener('click', (e) => { if (!e.target.classList.contains('close-toast')) { markNotificationRead(notifId); clearTimeout(timer); remove(); } });
        toast.querySelector('.close-toast').addEventListener('click', (e) => { e.stopPropagation(); markNotificationRead(notifId); clearTimeout(timer); remove(); });
    }

    function escapeHtml(text) {
        const d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }

    function markNotificationRead(notifId) {
        fetch('/api/notifications/mark_read', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notification_id: notifId })
        }).catch(err => console.error('Notif error:', err));
    }

    function fetchNotifications() {
        fetch('/api/notifications')
            .then(r => r.json())
            .then(data => { if (data.success && data.notifications?.length) data.notifications.forEach(n => showNotificationToast(n.title, n.message, n.id)); })
            .catch(() => {});
    }
    setTimeout(fetchNotifications, 2000);
    setInterval(fetchNotifications, 30000);

    // ============================================
    // BUTTON LOADING STATE HELPERS
    // ============================================

    function setButtonLoading(btn, loadingText = 'Loading...') {
        btn.disabled = true;
        btn._originalHTML = btn.innerHTML;
        btn.innerHTML = `<span class="btn-spinner"></span>${loadingText}`;
    }

    function resetButton(btn) {
        btn.disabled = false;
        if (btn._originalHTML !== undefined) btn.innerHTML = btn._originalHTML;
    }

    // ============================================
    // COPY BUTTONS FOR KEY CELLS & UTR CODES
    // ============================================

    function addCopyBtn(el, getText, label) {
        if (el.querySelector('.copy-cell-btn')) return;
        const btn = document.createElement('button');
        btn.className = 'copy-cell-btn';
        btn.innerHTML = '<i class="fas fa-copy"></i>';
        btn.title = 'Copy';
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            copyToClipboard(getText(), label);
            btn.innerHTML = '<i class="fas fa-check"></i>';
            setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i>'; }, 2000);
        });
        el.appendChild(btn);
    }

    document.querySelectorAll('.key-cell').forEach(cell => {
        addCopyBtn(cell, () => cell.childNodes[0]?.textContent?.trim() || cell.textContent.trim(), '🔑 Key copied!');
    });

    document.querySelectorAll('td code').forEach(code => {
        const td = code.parentElement;
        if (!td || td.querySelector('.copy-cell-btn')) return;
        const btn = document.createElement('button');
        btn.className = 'copy-cell-btn copy-cell-btn--inline';
        btn.innerHTML = '<i class="fas fa-copy"></i>';
        btn.title = 'Copy';
        btn.style.marginLeft = '6px';
        btn.addEventListener('click', () => {
            copyToClipboard(code.textContent.trim(), '📋 Copied!');
            btn.innerHTML = '<i class="fas fa-check"></i>';
            setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i>'; }, 2000);
        });
        code.after(btn);
    });

    // ============================================
    // PASSWORD SHOW / HIDE TOGGLES
    // ============================================

    document.querySelectorAll('.password-toggle').forEach(toggle => {
        toggle.addEventListener('click', function() {
            const input = this.previousElementSibling;
            if (!input) return;
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            this.innerHTML = show ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>';
        });
    });

    // Password confirmation live validation
    const pwInput  = document.getElementById('password');
    const pw2Input = document.getElementById('confirm_password');
    if (pwInput && pw2Input) {
        const check = () => {
            if (!pw2Input.value) { pw2Input.style.borderColor = ''; pw2Input.style.boxShadow = ''; return; }
            const match = pw2Input.value === pwInput.value;
            pw2Input.style.borderColor = match ? 'var(--accent-green)' : 'var(--accent-red)';
            pw2Input.style.boxShadow   = match ? '0 0 10px rgba(0,255,0,0.3)' : '0 0 10px rgba(255,68,68,0.3)';
        };
        pw2Input.addEventListener('input', check);
        pwInput.addEventListener('input', check);
    }

    // ============================================
    // PRODUCT SELECTION & KEY GENERATION
    // ============================================

    const productSelect  = document.getElementById('product-select');
    const daysSelection  = document.getElementById('days-selection');
    const daysSelect     = document.getElementById('days-select');
    const productDetails = document.getElementById('product-details');
    const costPerDay     = document.getElementById('cost-per-day');
    const totalCredits   = document.getElementById('total-credits');
    const originalPrice  = document.getElementById('original-price');
    const savings        = document.getElementById('savings');
    const generateBtn    = document.getElementById('generate-key');
    const generatedKeyDiv= document.getElementById('generated-key');
    const keyDisplay     = document.querySelector('.key-display');
    const copyKeyBtn     = document.getElementById('copy-key-btn');
    const reloadHint     = document.getElementById('reload-hint');

    let currentProduct = null;
    let reloadTimer    = null;

    function updateDiscountedPrice() {
        if (!currentProduct) return;
        fetch('/api/discounted_price', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_id: currentProduct.id, days: daysSelect.value })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                totalCredits.textContent = data.total_credits;
                if (originalPrice) originalPrice.textContent = data.original_total;
                if (savings)       savings.textContent       = data.savings;
                productDetails.style.display = 'block';
                generateBtn.disabled = false;
            }
        })
        .catch(() => {});
    }

    if (productSelect) {
        productSelect.addEventListener('change', function() {
            const opt = this.options[this.selectedIndex];
            if (this.value) {
                currentProduct = { id: this.value, cost: opt.dataset.cost, price: opt.dataset.price, type: opt.dataset.type };
                costPerDay.textContent = currentProduct.cost;
                daysSelection.style.display = 'block';
                updateDiscountedPrice();
            } else {
                daysSelection.style.display = 'none';
                productDetails.style.display = 'none';
                generateBtn.disabled = true;
                generatedKeyDiv.style.display = 'none';
                currentProduct = null;
                clearTimeout(reloadTimer);
            }
        });
    }
    if (daysSelect) daysSelect.addEventListener('change', updateDiscountedPrice);

    if (generateBtn) {
        generateBtn.addEventListener('click', function() {
            if (!currentProduct) return;
            setButtonLoading(generateBtn, 'Generating...');
            generatedKeyDiv.style.display = 'none';
            clearTimeout(reloadTimer);

            fetch('/generate_key', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_id: currentProduct.id, days: daysSelect.value })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    keyDisplay.textContent = data.key;
                    generatedKeyDiv.style.display = 'block';
                    showToast('🎉 Key generated! Copy it before page refreshes.', 'success', 8000);
                    // Auto-reload after 10s — plenty of time to copy
                    let secs = 10;
                    if (reloadHint) reloadHint.textContent = `Page refreshes in ${secs}s`;
                    const countdown = setInterval(() => {
                        secs--;
                        if (reloadHint) reloadHint.textContent = `Page refreshes in ${secs}s`;
                        if (secs <= 0) { clearInterval(countdown); location.reload(); }
                    }, 1000);
                    reloadTimer = setTimeout(() => { clearInterval(countdown); location.reload(); }, 10000);
                } else {
                    showAlert(data.error || 'Key generation failed.', 'error', 'Generation Failed');
                    resetButton(generateBtn);
                }
            })
            .catch(() => {
                showAlert('Network error. Please try again.', 'error');
                resetButton(generateBtn);
            });
        });
    }

    if (copyKeyBtn) {
        copyKeyBtn.addEventListener('click', function() {
            const key = keyDisplay?.textContent?.trim();
            if (key) {
                copyToClipboard(key, '🎉 Key copied to clipboard!');
                copyKeyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                setTimeout(() => { copyKeyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy Key'; }, 2500);
            }
        });
    }

    // ============================================
    // HWID RESET
    // ============================================

    const hwidResetAll = document.getElementById('hwid-reset-all');
    if (hwidResetAll) {
        hwidResetAll.addEventListener('click', async function() {
            const ok = await showConfirm('This will reset HWID for <strong>all your active licenses</strong>.', 'Reset All HWIDs', 'warning');
            if (!ok) return;
            setButtonLoading(hwidResetAll, 'Resetting...');
            fetch('/hwid_reset_all', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('✅ All HWIDs reset!', 'success'); setTimeout(() => location.reload(), 2000); } else { showAlert(data.error, 'error'); resetButton(hwidResetAll); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(hwidResetAll); });
        });
    }

    document.querySelectorAll('.btn-hwid-reset').forEach(btn => {
        btn.addEventListener('click', async function() {
            const ok = await showConfirm('Reset HWID for this license?', 'Reset HWID', 'warning');
            if (!ok) return;
            const licenseId = this.dataset.licenseId;
            setButtonLoading(this, 'Resetting...');
            const self = this;
            fetch('/hwid_reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ license_id: licenseId }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('✅ HWID reset!', 'success'); setTimeout(() => location.reload(), 2000); } else { showAlert(data.error, 'error'); resetButton(self); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
        });
    });

    // ============================================
    // ADMIN TABS
    // ============================================

    const tabs = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    if (tabs.length > 0) {
        tabs.forEach(tab => {
            tab.addEventListener('click', function() {
                const name = this.dataset.tab;
                tabs.forEach(t => t.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));
                this.classList.add('active');
                document.getElementById(name + '-tab')?.classList.add('active');
            });
        });
    }

    // ============================================
    // ADMIN — ADD PRODUCT
    // ============================================

    const addProductBtn  = document.getElementById('add-product-btn');
    const addProductForm = document.getElementById('add-product-form');
    const cancelProductBtn = document.getElementById('cancel-product');
    const saveProductBtn   = document.getElementById('save-product');

    addProductBtn?.addEventListener('click', () => { addProductForm.style.display = 'block'; addProductForm.scrollIntoView({ behavior: 'smooth' }); });
    cancelProductBtn?.addEventListener('click', () => {
        addProductForm.style.display = 'none';
        ['new-product-name','new-product-credits','new-product-price'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    });

    saveProductBtn?.addEventListener('click', function() {
        const name   = document.getElementById('new-product-name')?.value?.trim();
        const credits = document.getElementById('new-product-credits')?.value;
        const price   = document.getElementById('new-product-price')?.value;
        const keytype = document.getElementById('new-product-keytype')?.value;
        const pattern = document.getElementById('new-product-custom-pattern')?.value || '';
        if (!name || !credits || !price) { showAlert('Please fill all required fields.', 'warning', 'Missing Fields'); return; }
        setButtonLoading(this, 'Saving...');
        const self = this;
        fetch('/admin/add_product', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, credit_cost_per_day: credits, price_per_day: price, key_type: keytype, custom_key_pattern: pattern }) })
            .then(r => r.json())
            .then(data => { if (data.success) { showToast('✅ Product added!', 'success'); setTimeout(() => location.reload(), 1500); } else { showAlert(data.error || 'Failed', 'error'); resetButton(self); } })
            .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
    });

    // ============================================
    // ADMIN — EDIT PRODUCT MODAL
    // ============================================

    const editProductModal   = document.getElementById('edit-product-modal');
    const editProductId      = document.getElementById('edit-product-id');
    const editProductName    = document.getElementById('edit-product-name');
    const editProductCredits = document.getElementById('edit-product-credits');
    const editProductPrice   = document.getElementById('edit-product-price');
    const editProductKeyType = document.getElementById('edit-product-keytype');
    const editProductPattern = document.getElementById('edit-product-custom-pattern');
    const updateProductBtn   = document.getElementById('update-product');
    const closeModalBtn      = document.getElementById('close-modal');

    document.querySelectorAll('.btn-edit-product').forEach(btn => {
        btn.addEventListener('click', function() {
            const row = this.closest('tr');
            const cells = row.querySelectorAll('td');
            editProductId.value      = this.dataset.productId;
            editProductName.value    = cells[0].textContent.trim();
            editProductCredits.value = cells[1].textContent.trim();
            editProductPrice.value   = cells[2].textContent.trim().replace('₹','');
            const kt = cells[3].textContent.trim();
            Array.from(editProductKeyType.options).forEach(o => { if (o.value === kt) o.selected = true; });
            if (editProductPattern) editProductPattern.value = cells[4]?.textContent.trim() || '';
            editProductModal.style.display = 'flex';
        });
    });

    updateProductBtn?.addEventListener('click', function() {
        setButtonLoading(this, 'Updating...');
        const self = this;
        fetch('/admin/edit_product', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_id: editProductId.value, name: editProductName.value, credit_cost_per_day: editProductCredits.value, price_per_day: editProductPrice.value, key_type: editProductKeyType.value, custom_key_pattern: editProductPattern?.value || '' }) })
            .then(r => r.json())
            .then(data => { if (data.success) { showToast('✅ Product updated!', 'success'); setTimeout(() => location.reload(), 1500); } else { showAlert('Failed to update', 'error'); resetButton(self); } })
            .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
    });

    closeModalBtn?.addEventListener('click', () => { editProductModal.style.display = 'none'; });

    // ============================================
    // ADMIN — DELETE PRODUCT
    // ============================================

    document.querySelectorAll('.btn-delete-product').forEach(btn => {
        btn.addEventListener('click', async function() {
            const ok = await showConfirm('Delete this product? <strong>This cannot be undone.</strong>', 'Delete Product', 'danger');
            if (!ok) return;
            const productId = this.dataset.productId;
            setButtonLoading(this, 'Deleting...');
            const self = this;
            fetch('/admin/delete_product', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_id: productId }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('🗑️ Product deleted', 'info'); setTimeout(() => location.reload(), 1500); } else { showAlert('Failed to delete', 'error'); resetButton(self); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
        });
    });

    // ============================================
    // ADMIN — PAYMENTS
    // ============================================

    document.querySelectorAll('.btn-approve-payment').forEach(btn => {
        btn.addEventListener('click', async function() {
            const ok = await showConfirm('Approve this payment? Credits will be added to the user.', 'Approve Payment', 'info');
            if (!ok) return;
            const paymentId = this.dataset.paymentId;
            setButtonLoading(this, 'Approving...');
            const self = this;
            fetch('/admin/approve_payment', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payment_id: paymentId }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('✅ Payment approved — credits added!', 'success'); setTimeout(() => location.reload(), 2000); } else { showAlert(data.error || 'Failed', 'error'); resetButton(self); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
        });
    });

    document.querySelectorAll('.btn-reject-payment').forEach(btn => {
        btn.addEventListener('click', async function() {
            const reason = await showPrompt('Enter a rejection reason for the user:', 'Payment rejected by admin', 'Reject Payment', 'e.g. Invalid UTR, duplicate...');
            if (reason === null) return;
            const paymentId = this.dataset.paymentId;
            setButtonLoading(this, 'Rejecting...');
            const self = this;
            fetch('/admin/reject_payment', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payment_id: paymentId, reason: reason || 'Payment rejected by admin' }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('Payment rejected', 'warning'); setTimeout(() => location.reload(), 2000); } else { showAlert(data.error || 'Failed', 'error'); resetButton(self); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
        });
    });

    document.querySelectorAll('.btn-cancel-binance').forEach(btn => {
        btn.addEventListener('click', async function() {
            const ok = await showConfirm('Cancel this Binance order?', 'Cancel Order', 'warning');
            if (!ok) return;
            const orderId = this.dataset.orderId;
            setButtonLoading(this, 'Cancelling...');
            const self = this;
            fetch('/admin/cancel_binance_order', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ order_id: orderId }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('✅ Order cancelled', 'success'); setTimeout(() => location.reload(), 2000); } else { showAlert(data.error || 'Failed', 'error'); resetButton(self); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
        });
    });

    // ============================================
    // ADMIN — ADD CREDITS MODAL
    // ============================================

    const addCreditsModal   = document.getElementById('add-credits-modal');
    const addCreditsUsername= document.getElementById('add-credits-username');
    const addCreditsAmount  = document.getElementById('add-credits-amount');
    const confirmAddCredits = document.getElementById('confirm-add-credits');
    const closeCreditsModal = document.getElementById('close-credits-modal');

    document.querySelectorAll('.btn-add-credits').forEach(btn => {
        btn.addEventListener('click', function() {
            addCreditsUsername.value = this.dataset.username;
            addCreditsModal.style.display = 'flex';
            setTimeout(() => addCreditsAmount?.focus(), 100);
        });
    });

    confirmAddCredits?.addEventListener('click', function() {
        const credits = addCreditsAmount.value;
        if (!credits || credits < 1) { showAlert('Please enter a valid credit amount.', 'warning'); return; }
        setButtonLoading(this, 'Adding...');
        const self = this;
        const username = addCreditsUsername.value;
        fetch('/admin/add_credits', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, credits }) })
            .then(r => r.json())
            .then(data => { if (data.success) { showToast(`✅ Credits added to ${username}!`, 'success'); addCreditsModal.style.display = 'none'; addCreditsAmount.value = ''; setTimeout(() => location.reload(), 2000); } else { showAlert('Failed to add credits', 'error'); resetButton(self); } })
            .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
    });

    closeCreditsModal?.addEventListener('click', () => { addCreditsModal.style.display = 'none'; addCreditsAmount.value = ''; });

    // ============================================
    // ADMIN — DELETE USER
    // ============================================

    document.querySelectorAll('.btn-delete-user').forEach(btn => {
        btn.addEventListener('click', async function() {
            const username = this.dataset.username;
            const ok = await showConfirm(`Delete user <strong>"${escapeHtml(username)}"</strong>? All their data will be removed permanently.`, 'Delete User', 'danger');
            if (!ok) return;
            setButtonLoading(this, 'Deleting...');
            const self = this;
            fetch('/admin/delete_user', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('🗑️ User deleted', 'info'); setTimeout(() => location.reload(), 1500); } else { showAlert('Failed to delete user', 'error'); resetButton(self); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
        });
    });

    // ============================================
    // ADMIN — DELETE KEY
    // ============================================

    document.querySelectorAll('.btn-delete-key').forEach(btn => {
        btn.addEventListener('click', async function() {
            const ok = await showConfirm('Delete this license key permanently?', 'Delete Key', 'danger');
            if (!ok) return;
            const licenseId = this.dataset.licenseId;
            setButtonLoading(this, 'Deleting...');
            const self = this;
            fetch('/admin/delete_key', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ license_id: licenseId }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast('🗑️ Key deleted', 'info'); setTimeout(() => location.reload(), 1500); } else { showAlert('Failed to delete key', 'error'); resetButton(self); } })
                .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
        });
    });

    // ============================================
    // ADMIN — TOGGLE PRODUCT
    // ============================================

    document.querySelectorAll('.btn-toggle-product').forEach(btn => {
        btn.addEventListener('click', function() {
            const productId = this.dataset.productId;
            const isActive  = this.dataset.active === 'True' ? false : true;
            fetch('/admin/toggle_product', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_id: productId, is_active: isActive }) })
                .then(r => r.json())
                .then(data => { if (data.success) { showToast(isActive ? '✅ Product enabled' : '⏸️ Product disabled', 'info'); setTimeout(() => location.reload(), 1000); } });
        });
    });

    // Custom pattern field toggle
    document.getElementById('new-product-keytype')?.addEventListener('change', function() {
        const g = document.getElementById('custom-pattern-group');
        if (g) g.style.display = this.value === 'custom' ? 'block' : 'none';
    });

    // Key type management
    document.getElementById('add-keytype-btn')?.addEventListener('click', () => { document.getElementById('add-keytype-form').style.display = 'block'; });
    document.getElementById('cancel-keytype')?.addEventListener('click', () => { document.getElementById('add-keytype-form').style.display = 'none'; });
    document.getElementById('save-keytype')?.addEventListener('click', function() {
        const name = document.getElementById('new-keytype-name')?.value;
        const pat  = document.getElementById('new-keytype-pattern')?.value;
        const desc = document.getElementById('new-keytype-desc')?.value;
        if (!name || !pat) { showAlert('Name and pattern are required.', 'warning'); return; }
        setButtonLoading(this, 'Saving...');
        const self = this;
        fetch('/admin/add_key_type', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type_name: name, pattern: pat, description: desc }) })
            .then(r => r.json())
            .then(data => { if (data.success) { showToast('✅ Key type added!', 'success'); setTimeout(() => location.reload(), 1500); } else { showAlert(data.error, 'error'); resetButton(self); } });
    });

    // ============================================
    // ADMIN — SEND NOTIFICATION
    // ============================================

    const sendNotifBtn    = document.getElementById('send-notification-btn');
    const notifModal      = document.getElementById('notification-modal');
    const closeNotifModal = document.getElementById('close-notification-modal');
    const notifSubmit     = document.getElementById('send-notification-submit');
    const notifTitle      = document.getElementById('notification-title');
    const notifMessage    = document.getElementById('notification-message');
    const notifTarget     = document.getElementById('notification-target');
    const userListSelect  = document.getElementById('user-list-select');

    if (notifTarget && userListSelect) {
        fetch('/admin/get_users_list').then(r => r.json()).then(data => {
            if (data.success && data.users) {
                userListSelect.innerHTML = '<option value="">-- Select User --</option>';
                data.users.forEach(u => { userListSelect.innerHTML += `<option value="${u}">${u}</option>`; });
            }
        }).catch(() => {});
        notifTarget.addEventListener('change', function() { userListSelect.style.display = this.value === 'specific' ? 'block' : 'none'; });
    }

    sendNotifBtn?.addEventListener('click', () => { notifModal.style.display = 'flex'; });
    closeNotifModal?.addEventListener('click', () => { notifModal.style.display = 'none'; notifTitle.value = ''; notifMessage.value = ''; });

    notifSubmit?.addEventListener('click', function() {
        const title   = notifTitle.value.trim() || 'Announcement';
        const message = notifMessage.value.trim();
        if (!message) { showAlert('Please enter a notification message.', 'warning'); return; }
        const targetType = notifTarget.value;
        let targetUser = null;
        if (targetType === 'specific') {
            targetUser = userListSelect.value;
            if (!targetUser) { showAlert('Please select a user.', 'warning'); return; }
        }
        setButtonLoading(this, 'Sending...');
        const self = this;
        fetch('/admin/send_notification', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, message, target_user: targetUser }) })
            .then(r => r.json())
            .then(data => { if (data.success) { showToast('📢 Notification sent!', 'success'); notifModal.style.display = 'none'; notifTitle.value = ''; notifMessage.value = ''; resetButton(self); } else { showAlert(data.error || 'Failed to send', 'error'); resetButton(self); } })
            .catch(() => { showAlert('An error occurred', 'error'); resetButton(self); });
    });

    // Close modals on outside click
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) e.target.style.display = 'none';
    });

});
