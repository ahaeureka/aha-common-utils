"""参数元数据系统 - 类似 FastAPI 的参数约束

提供类似 FastAPI 的 Annotated[type, ParamMeta(...)] 机制，用于定义参数的描述、约束和验证规则。
"""
from typing import Any, Callable, Optional, Union


class ParamMeta:
    """参数元数据 - 类似 FastAPI 的 Query/Path/Body

    用于描述参数的约束、验证和文档信息。

    Examples:
        >>> from typing import Annotated
        >>> # 字符串参数，带长度限制
        >>> name: Annotated[str, ParamMeta(description="用户名", min_length=3, max_length=50)]
        >>>
        >>> # 数字参数，带范围限制
        >>> port: Annotated[int, ParamMeta(description="端口号", ge=1, le=65535)] = 8080
        >>>
        >>> # 可选参数
        >>> timeout: Annotated[Optional[int], ParamMeta(description="超时时间(秒)")] = None
    """

    def __init__(
        self,
        default: Any = ...,
        *,
        description: Optional[str] = None,
        title: Optional[str] = None,
        # 数值约束
        gt: Optional[Union[int, float]] = None,  # 大于
        ge: Optional[Union[int, float]] = None,  # 大于等于
        lt: Optional[Union[int, float]] = None,  # 小于
        le: Optional[Union[int, float]] = None,  # 小于等于
        multiple_of: Optional[Union[int, float]] = None,  # 倍数
        # 字符串约束
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,  # 正则表达式
        # 集合约束
        min_items: Optional[int] = None,
        max_items: Optional[int] = None,
        # 通用约束
        const: Optional[Any] = None,  # 固定值
        enum: Optional[list] = None,  # 枚举值
        # 自定义验证
        validator: Optional[Callable[[Any], bool]] = None,
        # 其他元数据
        examples: Optional[list] = None,
        deprecated: bool = False,
        **extra: Any,
    ):
        """初始化参数元数据

        Args:
            default: 默认值，... 表示必填
            description: 参数描述
            title: 参数标题
            gt: 大于此值
            ge: 大于等于此值
            lt: 小于此值
            le: 小于等于此值
            multiple_of: 必须是此值的倍数
            min_length: 字符串/列表最小长度
            max_length: 字符串/列表最大长度
            pattern: 正则表达式模式
            min_items: 集合最小元素数
            max_items: 集合最大元素数
            const: 固定值约束
            enum: 枚举值列表
            validator: 自定义验证函数
            examples: 示例值列表
            deprecated: 是否已弃用
            **extra: 其他自定义元数据
        """
        self.default = default
        self.description = description
        self.title = title

        # 数值约束
        self.gt = gt
        self.ge = ge
        self.lt = lt
        self.le = le
        self.multiple_of = multiple_of

        # 字符串约束
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern

        # 集合约束
        self.min_items = min_items
        self.max_items = max_items

        # 通用约束
        self.const = const
        self.enum = enum

        # 自定义验证
        self.validator = validator

        # 其他元数据
        self.examples = examples
        self.deprecated = deprecated
        self.extra = extra

    @property
    def is_required(self) -> bool:
        """是否为必填参数"""
        return self.default is ...

    def to_field_info(self) -> dict:
        """转换为 Pydantic Field 参数

        Returns:
            可用于 pydantic.Field() 的参数字典
        """
        field_kwargs = {}

        # 默认值
        if self.default is not ...:
            field_kwargs["default"] = self.default

        # 描述信息
        if self.description:
            field_kwargs["description"] = self.description
        if self.title:
            field_kwargs["title"] = self.title

        # 数值约束
        if self.gt is not None:
            field_kwargs["gt"] = self.gt
        if self.ge is not None:
            field_kwargs["ge"] = self.ge
        if self.lt is not None:
            field_kwargs["lt"] = self.lt
        if self.le is not None:
            field_kwargs["le"] = self.le
        if self.multiple_of is not None:
            field_kwargs["multiple_of"] = self.multiple_of

        # 字符串约束
        if self.min_length is not None:
            field_kwargs["min_length"] = self.min_length
        if self.max_length is not None:
            field_kwargs["max_length"] = self.max_length
        if self.pattern is not None:
            field_kwargs["pattern"] = self.pattern

        # 集合约束
        if self.min_items is not None:
            field_kwargs["min_items"] = self.min_items
        if self.max_items is not None:
            field_kwargs["max_items"] = self.max_items

        # 通用约束
        if self.const is not None:
            field_kwargs["const"] = self.const
        # pydantic v2 使用 Literal，这里先存储
        if self.enum is not None:
            field_kwargs["json_schema_extra"] = {"enum": self.enum}

        # 其他元数据
        if self.examples:
            field_kwargs["examples"] = self.examples
        if self.deprecated:
            field_kwargs["deprecated"] = self.deprecated

        # 合并额外元数据
        if self.extra:
            if "json_schema_extra" in field_kwargs:
                field_kwargs["json_schema_extra"].update(self.extra)
            else:
                field_kwargs["json_schema_extra"] = self.extra

        return field_kwargs

    def __repr__(self) -> str:
        attrs = []
        if self.description:
            attrs.append(f"description={self.description!r}")
        if self.default is not ...:
            attrs.append(f"default={self.default!r}")
        if self.ge is not None:
            attrs.append(f"ge={self.ge}")
        if self.le is not None:
            attrs.append(f"le={self.le}")
        if self.min_length is not None:
            attrs.append(f"min_length={self.min_length}")
        if self.max_length is not None:
            attrs.append(f"max_length={self.max_length}")
        return f"ParamMeta({', '.join(attrs)})"


# 便捷别名，类似 FastAPI
Param = ParamMeta
Query = ParamMeta
Field = ParamMeta
