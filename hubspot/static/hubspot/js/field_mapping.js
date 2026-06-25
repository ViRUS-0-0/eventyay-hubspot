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
});
