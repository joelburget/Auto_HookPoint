from Components.Diagnostics import check_auto_hook
from Components.AutoHooked import auto_hook
from .test_models import (
    SimpleModule, 
    SimpleModelWithModuleDict, 
    SimpleNestedModuleList, 
    ComplexNestedModule,
    small_llama_config,
    small_mixtral_config
)
from transformers.models.llama import LlamaForCausalLM
from transformers.models.mixtral import MixtralForCausalLM
import pytest
import torch
from typing import Any, Type, TypeVar, Dict

T = TypeVar('T')

#module instance, input 
def get_test_cases():
    return [
        (SimpleModule, {}, {'x' : torch.randn(1, 10)} ),
        (SimpleModelWithModuleDict, {}, {'x' : torch.randn(1, 10)} ),
        (SimpleNestedModuleList, {}, {'x' : torch.randn(1, 10)} ),
        (ComplexNestedModule, {}, {'x' : torch.randn(1, 10, 128)} ),
        (LlamaForCausalLM, {'config' : small_llama_config}, {'input_ids' : torch.randint(0, 1000, (1, 10))}),
        (MixtralForCausalLM, {'config' : small_mixtral_config}, {'input_ids' : torch.randint(0, 1000, (1, 10))})
    ]

@pytest.mark.parametrize(
    "module, init_kwargs, input_kwargs", 
    get_test_cases()
)
def test_check_auto_hook(
    module: Type[T], 
    init_kwargs : Dict[str, Any],
    input_kwargs : Dict[str, torch.Tensor]
):
    check_auto_hook(module, init_kwargs, input_kwargs, strict=True)