from torch import nn
from utils import has_implemented_forward, iterate_module
from transformer_lens.hook_points import HookPoint
from Components.AutoHooked import HookedInstance, auto_hook
from typing import Any, List, Union
from collections import Counter
from typing import TypeVar, Type
from inspect import isclass

T = TypeVar('T', bound=nn.Module)

def get_duplicates(lst : list[str]) -> list[str]:
    return [item for item, count in Counter(lst).items() if count > 1]

BUILT_IN_MODULES = [
    nn.Linear, nn.Conv1d, nn.Conv2d, nn.Conv3d, nn.ConvTranspose1d, nn.ConvTranspose2d, nn.ConvTranspose3d,
    nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d, nn.LayerNorm ,nn.LayerNorm, nn.Embedding,
    nn.RNN, nn.LSTM, nn.GRU, nn.RNNCell, nn.LSTMCell, nn.GRUCell, 
    # Add more built-in module types as needed
]

def generate_expected_hookpoints(model : Union[HookedInstance, nn.Module],  prefix='') -> list[str]:
    expected_hooks = set()

    if isinstance(model, HookedInstance):
        model = model._module

    for name, module in model.named_children():
        full_name = f"{prefix}.{name}" if prefix else name
        if isinstance(module, HookPoint):
            continue
        
        if isinstance(module, (nn.ModuleList, nn.Sequential, nn.ModuleDict)):
            #these are module containers only their children should be hooked
            for key, child in iterate_module(module):
                expected_hooks.update(generate_expected_hookpoints(child, f"{full_name}.{key}"))
            expected_hooks.update(generate_expected_hookpoints(module, full_name))
        elif not full_name.endswith('.hook_point'):
            expected_hooks.add(f"{full_name}.hook_point")  
            
            if not any(isinstance(module, built_in) for built_in in BUILT_IN_MODULES):
                expected_hooks.update(generate_expected_hookpoints(module, full_name))

    # Only add parameter hook points for non-built-in modules
    if not any(isinstance(model, built_in) for built_in in BUILT_IN_MODULES):
        for name, param in model.named_parameters(recurse=False):
            full_name = f"{prefix}.{name}" if prefix else name
            if not full_name.endswith('.hook_point'):
                expected_hooks.add(f"{full_name}.hook_point")
        
    return list(expected_hooks)
