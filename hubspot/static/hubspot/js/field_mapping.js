document.addEventListener('DOMContentLoaded', function() {
    var addButton = document.getElementById('add-form-row');
    var tableBody = document.getElementById('field-mapping-formset');
    var templateObj = document.getElementById('empty-form-template');

    if (!addButton || !tableBody || !templateObj) return;

    var template = templateObj.innerHTML;
    var prefix = tableBody.getAttribute('data-formset-prefix');
    var totalFormsInput = document.getElementById('id_' + prefix + '-TOTAL_FORMS');

    addButton.addEventListener('click', function(e) {
        e.preventDefault();
        var formCount = parseInt(totalFormsInput.value);
        var newRowHtml = template.replace(/__prefix__/g, formCount);

        // Add the new row
        var tempDiv = document.createElement('tbody');
        tempDiv.innerHTML = newRowHtml;
        var newRow = tempDiv.firstElementChild;
        tableBody.appendChild(newRow);

        // Update total forms count
        totalFormsInput.value = formCount + 1;

        // Re-bind remove buttons
        bindRemoveButtons(newRow);

        // Initialize select2 on the new row if available
        if (window.jQuery && $.fn.select2) {
            $(newRow).find('.select2-static').select2({
                theme: "bootstrap",
                language: $("body").attr("data-select2-locale")
            });
        }
    });

    function bindRemoveButtons(container) {
        var removeButtons = container.querySelectorAll('.remove-form-row');
        for (var i = 0; i < removeButtons.length; i++) {
            removeButtons[i].addEventListener('click', function(e) {
                e.preventDefault();
                var row = this.closest('tr');
                // Check the Django DELETE checkbox if it exists (existing saved rows)
                var deleteInput = row.querySelector('input[name$="-DELETE"]');
                if (deleteInput) {
                    // Mark for deletion — do NOT clear select values or Django
                    // will fail field-level required validation before it can
                    // honour the DELETE flag.
                    deleteInput.checked = true;
                    row.style.display = 'none';
                } else {
                    // Unsaved new row — hide it and blank its required fields so
                    // Django treats this slot as an empty ignored form. Do NOT
                    // decrement TOTAL_FORMS; Django uses form indices, not count,
                    // to locate forms, so removing a mid-list index breaks later ones.
                    row.style.display = 'none';
                    row.querySelectorAll('select, input[type="text"]').forEach(function(el) {
                        el.value = '';
                    });
                }
            });
        }
    }

    // Bind initially existing remove buttons (for newly added rows in empty formset)
    bindRemoveButtons(tableBody);

    var form = document.getElementById('field-mapping-form');
    if (form && form.getAttribute('data-is-fetching') === 'true') {
        var saveBtn = document.querySelector('.btn-save');
        if (saveBtn) saveBtn.disabled = true;

        var selects = document.querySelectorAll('select[name$="hubspot_property"]');
        selects.forEach(function(select) {
            select.disabled = true;
            
            if (window.jQuery) {
                var $select = $(select);
                setTimeout(function() {
                    var $container = $select.next('.select2-container');
                    var loaderHtml = '<div class="text-muted" style="padding: 6px;"><i class="fa fa-spinner fa-spin fa-fw"></i> Loading properties...</div>';
                    if ($container.length) {
                        $container.hide();
                        $container.after(loaderHtml);
                    } else {
                        $select.hide();
                        $select.after(loaderHtml);
                    }
                }, 100);
            }
        });

        setTimeout(function() {
            window.location.reload();
        }, 5000);
    }

    const conflictBox = document.getElementById('identifier-conflict-box');
    if (conflictBox) {
        const radios = document.querySelectorAll('.resolve-identifier-radio');
        const indicesStr = conflictBox.getAttribute('data-conflicting-indices');
        const conflictingIndices = indicesStr ? indicesStr.split(',').filter(s => s.trim().length > 0).map(s => parseInt(s, 10)) : [];
        let newIdentifierRowAdded = false;

        radios.forEach(function(radio) {
            radio.addEventListener('change', function() {
                const val = this.value;
                if (val === 'new') {
                    conflictingIndices.forEach(function(idx) {
                        const delCheckbox = document.getElementById('id_form-' + idx + '-DELETE');
                        if (delCheckbox) {
                            delCheckbox.checked = true;
                            delCheckbox.closest('tr').style.display = 'none';
                        }
                    });

                    if (!newIdentifierRowAdded) {
                        const addRowBtn = document.getElementById('add-form-row');
                        if (addRowBtn) {
                            addRowBtn.click();
                            const rows = document.querySelectorAll('#field-mapping-formset .formset-row');
                            if (rows.length > 0) {
                                const lastRow = rows[rows.length - 1];
                                lastRow.classList.add('dynamic-identifier-row');
                                const syncModeSelect = lastRow.querySelector('select[name$="-sync_mode"]');
                                if (syncModeSelect) {
                                    let hasIdentifier = false;
                                    for (let i = 0; i < syncModeSelect.options.length; i++) {
                                        if (syncModeSelect.options[i].value === 'identifier') {
                                            hasIdentifier = true;
                                            break;
                                        }
                                    }
                                    if (!hasIdentifier) {
                                        syncModeSelect.add(new Option('Identifier', 'identifier'));
                                    }
                                    syncModeSelect.value = 'identifier';
                                    syncModeSelect.classList.add('sync-mode-locked');
                                }
                                lastRow.classList.add('highlight-row-temp');
                                setTimeout(function() {
                                    lastRow.classList.remove('highlight-row-temp');
                                }, 1000);
                                
                                // Move to the top of the table
                                lastRow.parentNode.insertBefore(lastRow, lastRow.parentNode.firstChild);

                                // Scroll to the new row
                                lastRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            }
                        }
                        newIdentifierRowAdded = true;
                    } else {
                        const dynRow = document.querySelector('.dynamic-identifier-row');
                        if (dynRow) {
                            dynRow.style.display = '';
                            const delCheckbox = dynRow.querySelector('input[id$="-DELETE"]');
                            if (delCheckbox) delCheckbox.checked = false;
                        }
                    }
                } else {
                    const dynRow = document.querySelector('.dynamic-identifier-row');
                    if (dynRow) {
                        dynRow.style.display = 'none';
                        const delCheckbox = dynRow.querySelector('input[id$="-DELETE"]');
                        if (delCheckbox) delCheckbox.checked = true;
                    }
                    
                    const keepIdx = parseInt(val, 10);
                    conflictingIndices.forEach(function(idx) {
                        const delCheckbox = document.getElementById('id_form-' + idx + '-DELETE');
                        if (delCheckbox) {
                            if (idx === keepIdx) {
                                delCheckbox.checked = false;
                                delCheckbox.closest('tr').style.display = '';
                                const syncModeSelect = document.getElementById('id_form-' + idx + '-sync_mode');
                                if (syncModeSelect) syncModeSelect.value = 'identifier';
                            } else {
                                delCheckbox.checked = true;
                                delCheckbox.closest('tr').style.display = 'none';
                            }
                        }
                    });
                }
            });
        });
    }
});
