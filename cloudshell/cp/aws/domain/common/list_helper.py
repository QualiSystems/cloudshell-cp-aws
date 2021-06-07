def first_or_default(lst, lambda_expression):
    return next(filter(lambda_expression, lst), None)
