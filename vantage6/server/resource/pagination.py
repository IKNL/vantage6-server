import math
from urllib.parse import urlencode

import flask

class Page:

    def __init__(self, items, page, page_size, total):
        self.items = items
        self.previous_page = None
        self.next_page = None
        self.has_previous = page > 1
        if self.has_previous:
            self.previous_page = page - 1
        previous_items = (page - 1) * page_size
        self.has_next = previous_items + len(items) < total
        if self.has_next:
            self.next_page = page + 1
        self.total = total
        self.pages = int(math.ceil(total / float(page_size)))

def paginate(query, request):

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    if page <= 0:
        raise AttributeError('page needs to be >= 1')
    if per_page <= 0:
        raise AttributeError('per_page needs to be >= 1')

    items = query.limit(per_page).offset((page - 1) * per_page).all()
    # We remove the ordering of the query since it doesn't matter for getting a count and
    # might have performance implications as discussed on this Flask-SqlAlchemy issue
    # https://github.com/mitsuhiko/flask-sqlalchemy/issues/100
    total = query.order_by(None).count()
    return Page(items, page, per_page, total)

def generate_pagination_header_link(request: flask.request, page: Page):

    original_arguments = request.args.copy()
    template = '<{url}>;rel={rel},'

    if 'page' not in original_arguments:
        original_arguments['page'] = 1
    if 'per_page' not in original_arguments:
        original_arguments['per_page'] = 10

    link = template.format(url=urlencode(original_arguments), rel='self')

    if page.has_next:
        original_arguments['page'] = page.next_page
        link += template.format(url=urlencode(original_arguments), rel='next')

    if page.has_previous:

        original_arguments['page'] = page.previous_page
        link += template.format(url=urlencode(original_arguments), rel='previous')


    original_arguments['page'] = 1
    link += template.format(url=urlencode(original_arguments), rel='first')


    original_arguments['page'] = page.pages
    link += template.format(url=urlencode(original_arguments), rel='last')

    return link