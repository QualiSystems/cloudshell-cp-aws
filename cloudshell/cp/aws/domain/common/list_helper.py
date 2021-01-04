def first_or_default(lst, lambda_expression):
    return next(filter(lambda_expression, lst), None)


def single(lst, lambda_expression):
    return next(filter(lambda_expression, lst))


def index_of(lst, predicate):
    gen = (index for index, item in enumerate(lst) if predicate(item))
    return next(gen, None)
