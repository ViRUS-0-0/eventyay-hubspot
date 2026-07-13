$(function () {
    function updateRetryButton() {
        var anyChecked = $('input[name="records"]:checked').length > 0;
        $('#btn-retry-selected').prop('disabled', !anyChecked);
    }

    $(document).on('change', 'input[type="checkbox"]', function() {
        setTimeout(updateRetryButton, 50);
    });
    updateRetryButton();
});
