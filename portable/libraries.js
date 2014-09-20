/* ----------------------------------------------------------------------------
 * Global configuration and state
 * ----------------------------------------------------------------------------
 */

var DOMAIN = 'memoryoftheworld.org'
//var DOMAIN = 'web.dokr'
var PREFIX_URL = 'https://www';
//var PREFIX_URL = 'http://www';
var ITEMS_PER_PAGE = 16;
var STATE = {
    page: 1,
    query: {
        'authors': '',
        'titles': '',
        'search_all': '',
        'librarian': '',
    }
};

var state_field_mapping = {
    'author': '#authors',
    'title': '#titles',
    'metadata': '#search_all',
    'librarian': '#librarian'
};

/* ----------------------------------------------------------------------------
 * Browser history stuff
 * ----------------------------------------------------------------------------
 */

var push_to_history = function() {
    var data = {};
    _.each(state_field_mapping, function(field, property) {
        data[property] = $(field).val();
    });
    data.page = STATE.page;
    var serialized = $.param(data);
    history.pushState(data, '', '#'+serialized);
};

/* ----------------------------------------------------------------------------
 * Precompile templates
 * ----------------------------------------------------------------------------
 */

var author_string_parts_tmpl = _.template($('#string-parts-tmpl').text().trim()),
    book_string_parts_tmpl = _.template($('#book-parts-tmpl').text().trim()),
    book_content_tmpl = _.template($('#book-content-tmpl').text().trim()),
    book_modal_tmpl = _.template($('#book-modal-tmpl').text().trim());

/* ----------------------------------------------------------------------------
 * Generate dictionaries for the html templates.
 * These functions should be mocked when this file is used by portable library
 * ----------------------------------------------------------------------------
 */

if(!window.gen_book_string_parts) {
    window.gen_book_string_parts = function (base_url, format, book) {
        book.application_id = "/" + book.application_id;
        return {
            'base_url': base_url + '/get/',
            'format': format,
            'book': book,
            'portable_book': '.',
            'portable_format': ''
        }
    }
};

if(!window.gen_book_content) {
    window.gen_book_content = function (base_url, book, authors, formats) {
        return {
            'base_url': base_url,
            'book': book,
            'book_title_stripped': ' ' + book.title.replace(/\?/g, ''),
            'authors': authors,
            'formats': formats,
            'get_cover': '/get/cover',
            'get_opf' : '/get/opf/',
            'portable_cover': '',
            'portable_opf': ''
        }
    }
};

if(!window.gen_book_modal) {
    var gen_book_modal = function (base_url, book, formats) {
        return {
            'base_url': base_url,
            'book': book,
            'book_title_stripped': ' ' + book.title.replace(/\?/g, ''),
            'formats': formats,
            'get_cover': '/get/cover/',
            'get_opf': '/get/opf/',
            'portable_cover': '',
            'portable_opf': ''
        }
    }
};

/* ----------------------------------------------------------------------------
 * Renders single book
 * ----------------------------------------------------------------------------
 */

var render_book = function(i, book) {
    var formats = '',
        base_url = [ PREFIX_URL, book.tunnel, '.', DOMAIN ].join(''),
        authors = '<div id="authorz">';
    
    book.formats.map(function (format) {
        var string_parts = book_string_parts_tmpl(
            gen_book_string_parts(base_url, format, book));
        formats = formats + " " + string_parts;
    });

    book.authors.map(function (author) {
        var author_s = author.replace("'", " "),
            author_param = 'search_author("' + author_s + '")',
            author_html = author_string_parts_tmpl({
              'author_s': author_s,
              'author': author
            });
        authors = authors + author_html;
    });

    $(document).on('click', '.author', function(e) {
      search_author($(this).data('authors'));
    });

    var last_comma = authors.lastIndexOf(',');
    authors = authors.substr(0, last_comma) +
        authors.substr(last_comma + 1) + '</div>';
    var book_content = book_content_tmpl(gen_book_content(
        base_url, book, authors, formats));
    $('#content').append(book_content);
};

/* ----------------------------------------------------------------------------
 * Main ajax entry point
 * ----------------------------------------------------------------------------
 */

var render_page = function () {
    push_to_history();

    $.ajax({
        type: 'POST',
        url: 'get_books',
        contentType: 'application/json',
        processData: false,
        data: JSON.stringify(STATE),
        dataType: 'json',
        success: function (data) {
            parse_response(data);
        }
    });
};

/* --------------------------------------------------------------------------*/

var parse_response = function (data) {
    update_autocomplete(data);
    update_pagination_info(data['on_page'], data['total']);
    if (data['next_page'] === null) {
        modify_button('#next_page', 'not-active');
    } else {
        modify_button('#next_page', 'active');
    };
    $('#content').empty();
    $.each(data['books'], render_book);
    setup_modal();
};

/* --------------------------------------------------------------------------*/

var setup_modal = function () {
    $('.more_about').click(function(e) {
        var uuid = $(this).attr('rel');
        $.getJSON('book', {uuid: uuid}).done(function( book ) {
            var formats = '',
            base_url = [ PREFIX_URL, book.tunnel, '.', DOMAIN ].join('');
            book.formats.map(function (format) {
                var string_parts = book_string_parts_tmpl(
                    gen_book_string_parts(base_url, format, book));
                formats = formats + " " + string_parts;
            });
            modal_html = book_modal_tmpl(
                gen_book_modal(base_url, book, formats));
            var modal = $(modal_html);
            modal.dialog({
                autoOpen: false,
                modal: true,
                minHeight: 300,
                minWidth: 500,
                position: { my: "center top", at: "center top"},
            });
            modal.dialog("open");
        });
        e.preventDefault();
    });
};

/* --------------------------------------------------------------------------*/

var update_pagination_info = function (items_on_page, total_num_of_items) {
    if (total_num_of_items == 0) {
        $('#page-msg').attr('value', '0 books');
        return;
    }
    var offset = (STATE.page-1) * ITEMS_PER_PAGE + 1;
    var total = 100;
    var msg = ['HOME (',
               offset,
               '-',
               offset + items_on_page - 1,
               'out of',
               total_num_of_items,
               'books )'].join(' ');
    $('#page-msg').attr('value', msg);
};

/* --------------------------------------------------------------------------*/

var update_autocomplete = function(data) {
    $('#authors').autocomplete({source: data['authors'],
                                minLength:2});
    $('#titles').autocomplete({source: data['titles'],
                               minLength:2});
    $('#librarian').empty()
    $('#librarian').append('<option value="">All librarians</option>'); 
    $.each(data['librarians'], function(index, item) {
        $('#librarian').append('<option value="' + item + '">' + item + '</option>'); 
    });
};

/* --------------------------------------------------------------------------*/

var next_page = function () {
    STATE.page += 1;
    modify_button('#prev_page', 'active');
    render_page();
};

/* --------------------------------------------------------------------------*/

var prev_page = function () {
    STATE.page -= 1;
    modify_button('#next_page', 'active');
    $('#next_page').show();
    if (STATE.page <= 1) {
        modify_button('#prev_page', 'not-active');
    }
    render_page();
};

/* ----------------------------------------------------------------------------
 * Adds complete toolbar to the top of the page
 * ----------------------------------------------------------------------------
 */

var init_toolbar = function () {
    $('#prev_page').click(function () {prev_page(); });
    $('#next_page').click(function () {next_page(); });
    $('#page-msg').click(function () {
      // going back to the homepage lists ALL books in the DB
      // (i.e. resets the search)
      _.each(state_field_mapping, function(field, property) {
        $(field).val('');
      });

      window.location.hash = '';
      location.reload();
    });
    $('#search').click(function() {
        search_query();
    });
    modify_button('#prev_page', 'not-active');
    $('#authors, #titles, #search_all').bind('keydown',function(e) {
        /* if enter is pressed */
        if(e.which == 13) {
            search_query();
        }
    })
};

/* ----------------------------------------------------------------------------
 * Changes state of the prev/next page buttons
 * ----------------------------------------------------------------------------
 */

var modify_button = function (button, state) {
    var elem = $(button);
    if (state == 'active') {
        elem.attr('disabled', false);
        elem.removeClass('not-active');
        elem.addClass('active');
    } else if (state == 'not-active') {
        elem.attr('disabled', true);
        elem.removeClass('active');
        elem.addClass('not-active');
    }
};

/* --------------------------------------------------------------------------*/

var search_query = function () {
    q = {};
    q.authors = $('#authors').val();
    q.titles = $('#titles').val();
    q.search_all = $('#search_all').val();
    q.librarian = $('#librarian').val();
    STATE.query = q;
    STATE.page = 1;
    render_page();
};

/* ----------------------------------------------------------------------------
 * Handle onload browser history
 * ----------------------------------------------------------------------------
 */

var handle_hash_state = function(event) {
    var deserialized = $.deparam(event.state);
    if (deserialized == null) return;
    _.each(state_field_mapping, function(field, property) {
        $(field).val(deserialized[property]);
    });
    if (deserialized.hasOwnProperty('page')) {
        STATE.page = parseInt(deserialized['page'], 10);
    }
    return search_query();
};

/* --------------------------------------------------------------------------*/

var search_author = function (author) {
    $('#authors').val(author);
    search_query();
};

/* --------------------------------------------------------------------------*/

$(document).ajaxStart(function () { 
    $('body').addClass("loading"); 
});

/* --------------------------------------------------------------------------*/

$(document).ajaxStop(function () { 
    $('body').removeClass("loading"); 
});

/* --------------------------------------------------------------------------*/

var init_page = function () {
    init_toolbar();
    /* do not display tooltip for modal close button (it gets automatically
     displayed */
    $(document).tooltip({items: '*:not(.ui-dialog-titlebar-close)'});
    if (window.location.hash != '') {
      var state = window.location.hash.substr(1);
      handle_hash_state(state);
    } else {
      render_page();
    }
    window.onpopstate = handle_hash_state;
};

/* --------------------------------------------------------------------------*/

$(document).ready(function () {
    init_page();
});
