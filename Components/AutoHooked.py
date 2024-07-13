from __future__ import annotations
from inspect import isclass
import itertools
from torch import nn
import torch
from transformer_lens.hook_points import HookPoint, HookedRootModule
from typing import (
    Generator,
    TypeVar, 
    Generic, 
    Union, 
    Type, 
    Any, 
    Callable, 
    get_type_hints, 
    ParamSpec, 
    Optional, 
    Set, 
    TypeVar, 
    Type, 
    Union, 
    cast, 
    overload
)
from inspect import isclass
import functools
from torch.nn.modules.module import Module

#these are modules where we will not iterate over their parameters
BUILT_IN_MODULES = [
    nn.Linear, nn.Conv1d, nn.Conv2d, nn.Conv3d, nn.ConvTranspose1d, nn.ConvTranspose2d, nn.ConvTranspose3d,
    nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d, nn.LayerNorm , nn.LayerNorm,
    nn.RNN, nn.LSTM, nn.GRU, nn.RNNCell, nn.LSTMCell, nn.GRUCell, 
    # Add more built-in module types as needed
]

T = TypeVar('T', bound=nn.Module)
P = TypeVar('P', bound=nn.Parameter)

@overload
def auto_hook(module: T) -> HookedModule[T]:
    ...

@overload
def auto_hook(module: P) -> HookedParameter:
    ...

def auto_hook(module: Union[T, P]) -> Union[HookedModule[T], HookedParameter]:
    '''
    This function wraps either a module instance or a module class and returns a type that
    preserves the original module's interface plus an additional unwrap method.
    '''
    assert not isinstance(module, HookedModule) or isinstance(module, HookedParameter), "Module is already hooked"
    
    if isinstance(module, nn.Module):
        Hooked = HookedModule(module) # type: ignore
        #NOTE we set the unwrap method to just return module_or_class
        Hooked.unwrap = lambda: module # type: ignore
        Hooked = cast(HookedModule[T], Hooked)
    elif isinstance(module, (nn.Parameter, torch.Tensor)):
        Hooked = HookedParameter(module) # type: ignore
        Hooked = cast(HookedModule[T], Hooked)
    else:
        raise ValueError(
            f"Module type {type(module)} is not supported should, "
            "be one of nn.Module or nn.Parameter/torch.Tensor"
        )
    return Hooked


class HookedParameter(HookedRootModule):
    def __init__(self, parameter: nn.Parameter):
        super().__init__()
        self.hook_point = HookPoint()
        self.param = parameter
        self.setup()

    def setup(self):
        self.mod_dict = {'hook_point': self.hook_point, 'param': self.param}  # Add this line
        self.hook_dict = {'hook_point': self.hook_point}

    def unwrap(self) -> nn.Parameter:
        return self.param

    def _apply_hook(self, result):
        return self.hook_point(result)

    def __add__(self, other):
        return self._apply_hook(self.param.__add__(other))

    def __radd__(self, other):
        return self._apply_hook(self.param.__radd__(other))

    def __sub__(self, other):
        return self._apply_hook(self.param.__sub__(other))

    def __rsub__(self, other):
        return self._apply_hook(self.param.__rsub__(other))

    def __mul__(self, other):
        return self._apply_hook(self.param.__mul__(other))

    def __rmul__(self, other):
        return self._apply_hook(self.param.__rmul__(other))


class HookedModule(HookedRootModule, Generic[T]):
    def __init__(self, module: T):
        super().__init__()
        # NOTE we need to name it in this way to not 
        # to avoid infinite regress and override

        
        self._module = module
        if not hasattr(self._module, 'hook_point'):
            self.hook_point = HookPoint()
        
        self._create_forward()
        self._wrap_submodules()
        self.setup()

    def setup(self):
        '''
        Same as HookedRootModule.setup() except using self.modules() instead of self.named_modules() 
        to avoid overwriting pytorch's named_modules()
        '''
        self.mod_dict = {}
        self.hook_dict = {}
        for name, module in self.named_modules():
            if name:
                module.name = name
                self.mod_dict[name] = module
                if isinstance(module, HookPoint):
                    self.hook_dict[name] = module

    #NOTE a private method used to iterate ove
    def _module_iterator(
        self, 
        use_names: bool = True, 
        memo: Set[Module] | None = None, 
        prefix: str = ''
    ) -> Generator[Union[tuple[str, Module], Module], None, None]:
        if memo is None:
            memo = set()

        if self not in memo:
            memo.add(self)
            yield (prefix, self) if use_names else self

            for name, module in self._module.named_children():
                if module not in memo:
                    submodule_prefix = prefix + ('.' if prefix else '') + name
                    if isinstance(module, HookedModule):
                        yield from module._module_iterator(use_names, memo, submodule_prefix)
                    else:
                        yield (submodule_prefix, module) if use_names else module
                        if hasattr(module, 'named_modules'):
                            yield from module.named_modules(memo, submodule_prefix)

            if hasattr(self, 'hook_point'):
                hook_point_prefix = prefix + ('.' if prefix else '') + 'hook_point'
                yield (hook_point_prefix, self.hook_point) if use_names else self.hook_point

    def named_modules(
        self, 
        memo: Set[Module] | None = None, 
        prefix: str = '', 
        remove_duplicate: bool = True
    )-> Generator[tuple[str, Module], None, None]:
        return self._module_iterator(use_names=True, memo=memo, prefix=prefix) #type: ignore

    def modules(
        self, 
        memo: Set[Module] | None = None
    ):
        return self._module_iterator(use_names=False, memo=memo)

    def new_attr_fn(self, name: str) -> Any:
        return getattr(self._module, name)
    
    #NOTE we override the nn.Module implementation to use _module only
    #NOTE this is not an ideal approach b

    def unwrap_instance(self) -> T:
        for name, submodule in self._module.named_children():
            if isinstance(submodule, (nn.ModuleList, nn.Sequential)):
                unHooked_container = type(submodule)()
                for m in submodule:
                    unHooked_container.append(m.unwrap_instance() if isinstance(m, HookedModule) else m)
                setattr(self._module, name, unHooked_container)
            elif isinstance(submodule, nn.ModuleDict):
                unHooked_container = type(submodule)()
                for key, m in submodule.items():
                    unHooked_container[key] = m.unwrap_instance() if isinstance(m, HookedModule) else m
                setattr(self._module, name, unHooked_container)
            elif isinstance(submodule, HookedModule):
                setattr(self._module, name, submodule.unwrap_instance())
        return self._module        

    def _wrap_submodules(self):
        parameter_hook_dict = {}
        if not any(isinstance(self._module, built_in_module) for built_in_module in BUILT_IN_MODULES):
            #RECURSE is set to false to avoid getting all sub params
            for name, submodule in self._module.named_parameters(recurse=False):
                if isinstance(submodule, nn.Parameter):
                    #NOTE IT IS NOT EASY TO WRAP A HOOKPOINT AROUND NN.PARAMETER
                    #THIS IS CURRENTLY NOT SUPPORTED BUT WILL BE NEEDED TO SUPPORT
                    #NOTE we can still set the hookpoint, but it doesnt provide meaningful utility 
                    # as it is hard to wrap the output of NN.PARAMETER 
                    parameter_hook_dict[f'{name}.hook_point'] = HookPoint()
                    #setattr(self._module, f'{name}.hook_point', HookPoint()) 
        
            for hook_name, hook_point in parameter_hook_dict.items():
                setattr(self._module, hook_name, hook_point)

        for name, submodule in self._module.named_children():
            print(f"wrapping submodule name {name}, submodule: {submodule}")
            if isinstance(submodule, HookPoint):
                continue

            elif isinstance(submodule, (nn.ModuleList, nn.Sequential)):
                Hooked_container = type(submodule)() #initialize the container
                for i, m in enumerate(submodule):
                    Hooked_container.append(auto_hook(m))
                print(f"setting attr {name} to {Hooked_container}")
                setattr(self._module, name, Hooked_container)
            elif isinstance(submodule, nn.ModuleDict):
                Hooked_container = type(submodule)()
                for key, m in submodule.items():
                    Hooked_container[key] = auto_hook(m)
                setattr(self._module, name, Hooked_container)
            else:
                setattr(self._module, name, auto_hook(submodule))

    def _create_forward(self):
        original_forward = self._module.forward
        original_type_hints = get_type_hints(original_forward)

        @functools.wraps(original_forward)
        def new_forward(*args: Any, **kwargs: Any) -> Any:
            return self.hook_point(original_forward(*args, **kwargs))

        new_forward.__annotations__ = original_type_hints
        self.forward = new_forward  # Assign to instance, not class

    def list_all_hooks(self):
        return [(hook, hook_point) for hook, hook_point in self.hook_dict.items()] 
    