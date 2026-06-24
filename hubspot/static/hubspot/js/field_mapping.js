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
                    // Unsaved new row — safe to remove from DOM entirely
                    row.parentNode.removeChild(row);
                    // Decrement TOTAL_FORMS so Django ignores this slot
                    var prefix = tableBody.getAttribute('data-formset-prefix');
                    var totalFormsInput = document.getElementById('id_' + prefix + '-TOTAL_FORMS');
                    if (totalFormsInput) {
                        totalFormsInput.value = parseInt(totalFormsInput.value) - 1;
                    }
                }
            });
        }
    }

    // Bind initially existing remove buttons (for newly added rows in empty formset)
    bindRemoveButtons(tableBody);
});
