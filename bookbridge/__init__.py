"""bookbridge — 把任何 PDF 变成你母语的精校 ePub。

便捷用法：
    from bookbridge.convert import convert, Converter, directions
注意：不要在本 __init__ 里 `from .convert import convert`，那会让函数名
`convert` 盖住同名子模块 `bookbridge.convert`，导致 `import bookbridge.convert` 拿到函数。
"""

__version__ = "0.1.0"
