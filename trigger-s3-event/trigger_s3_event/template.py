class FormatValue:
    def __init__(self, format_str: str):
        self.format_str = format_str

    def format(self, **kwargs):
        return eval(self.format_str, kwargs)


def replace(template, **kwargs):
    if isinstance(template, dict):
        return {replace(k, **kwargs): replace(v, **kwargs) for k, v in template.items()}

    if isinstance(template, list):
        return [replace(v, **kwargs) for v in template]

    if isinstance(template, FormatValue):
        return template.format(**kwargs)

    return template
