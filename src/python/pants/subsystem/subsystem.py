# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import inspect
from typing import Dict, Tuple

from pants.option.optionable import Optionable
from pants.option.scope import ScopeInfo
from pants.subsystem.subsystem_client_mixin import SubsystemClientMixin, SubsystemDependency


class SubsystemError(Exception):
  """An error in a subsystem."""


class Subsystem(SubsystemClientMixin, Optionable):
  """A separable piece of functionality that may be reused across multiple tasks or other code.

  Subsystems encapsulate the configuration and initialization of things like JVMs,
  Python interpreters, SCMs and so on.

  Subsystem instances can be global or per-optionable. Global instances are useful for representing
  global concepts, such as the SCM used in the workspace. Per-optionable instances allow individual
  Optionable objects (notably, tasks) to have their own configuration for things such as artifact
  caches.

  Each subsystem type has an option scope. The global instance of that subsystem initializes
  itself from options in that scope. An optionable-specific instance initializes itself from options
  in an appropriate subscope, which defaults back to the global scope.

  For example, the global artifact cache options would be in scope `cache`, but the
  compile.java task can override those options in scope `cache.compile.java`.

  Subsystems may depend on other subsystems, and therefore mix in SubsystemClientMixin.

  :API: public
  """
  options_scope_category = ScopeInfo.SUBSYSTEM

  class UninitializedSubsystemError(SubsystemError):
    def __init__(self, class_name, scope):
      super().__init__(
        f'Subsystem "{class_name}" not initialized for scope "{scope}". Is subsystem missing'
        'from subsystem_dependencies() in a task? '
      )

  @classmethod
  def is_subsystem_type(cls, obj):
    return inspect.isclass(obj) and issubclass(obj, cls)

  @classmethod
  def scoped(cls, optionable, removal_version=None, removal_hint=None):
    """Returns a dependency on this subsystem, scoped to `optionable`.

    :param removal_version: An optional deprecation version for this scoped Subsystem dependency.
    :param removal_hint: An optional hint to accompany a deprecation removal_version.

    Return value is suitable for use in SubsystemClientMixin.subsystem_dependencies().
    """
    return SubsystemDependency(cls, optionable.options_scope, removal_version, removal_hint)

  @classmethod
  def get_scope_info(cls, subscope=None):
    cls.validate_scope_name_component(cls.options_scope)
    if subscope is None:
      return super().get_scope_info()
    else:
      return ScopeInfo(cls.subscope(subscope), ScopeInfo.SUBSYSTEM, cls)

  # The full Options object for this pants run.  Will be set after options are parsed.
  # TODO: A less clunky way to make option values available?
  _options = None

  @classmethod
  def set_options(cls, options):
    cls._options = options

  @classmethod
  def is_initialized(cls):
    return cls._options is not None

  # A cache of (cls, scope) -> the instance of cls tied to that scope.
  _scoped_instances: Dict[Tuple["Subsystem", str], "Subsystem"] = {}

  @classmethod
  def global_instance(cls) -> "Subsystem":
    """Returns the global instance of this subsystem.

    :API: public

    :returns: The global subsystem instance.
    """
    return cls._instance_for_scope(cls.options_scope)  # type: ignore

  @classmethod
  def scoped_instance(cls, optionable: Optionable) -> "Subsystem":
    """Returns an instance of this subsystem for exclusive use by the given `optionable`.

    :API: public

    :param optionable: An optionable type or instance to scope this subsystem under.
    :returns: The scoped subsystem instance.
    """
    if not isinstance(optionable, Optionable) and not issubclass(optionable, Optionable):
      raise TypeError('Can only scope an instance against an Optionable, given {} of type {}.'
                      .format(optionable, type(optionable)))
    return cls._instance_for_scope(cls.subscope(optionable.options_scope))

  @classmethod
  def _instance_for_scope(cls, scope: str) -> "Subsystem":
    if cls._options is None:
      raise cls.UninitializedSubsystemError(cls.__name__, scope)
    key = (cls, scope)
    if key not in cls._scoped_instances:
      cls._scoped_instances[key] = cls(scope, cls._options.for_scope(scope))
    return cls._scoped_instances[key]

  @classmethod
  def reset(cls, reset_options=True):
    """Forget all option values and cached subsystem instances.

    Used primarily for test isolation and to reset subsystem state for pantsd.
    """
    if reset_options:
      cls._options = None
    cls._scoped_instances = {}

  def __init__(self, scope: str, scoped_options) -> None:
    """Note: A subsystem has no access to options in scopes other than its own.

    TODO: We'd like that to be true of Tasks some day. Subsystems will help with that.

    Code should call scoped_instance() or global_instance() to get a subsystem instance.
    It should not invoke this constructor directly.

    :API: public
    """
    super().__init__()
    self._scope = scope
    self._scoped_options = scoped_options
    self._fingerprint = None

  # It's safe to override the signature from Optionable because we validate
  # that every Optionable has `options_scope` defined as a `str` in the __init__. This code is
  # complex, though, and may be worth refactoring.
  @property
  def options_scope(self) -> str:  # type: ignore
    return self._scope

  @property
  def options(self):
    """Returns the option values for this subsystem's scope.

    :API: public
    """
    return self._scoped_options

  def get_options(self):
    """Returns the option values for this subsystem's scope.

    :API: public
    """
    return self._scoped_options
