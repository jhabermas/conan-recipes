from conans import ConanFile, tools
from conans.errors import ConanInvalidConfiguration
import os
import sys


class TensorFlowConan(ConanFile):
    name = "tensorflow"
    version = "2.3.0"
    description = "https://www.tensorflow.org/"
    topics = ("conan", "tensorflow", "ML")
    url = "https://github.com/bincrafters/conan-tensorflow"
    homepage = "The core open source library to help you develop and train ML models"
    license = "Apache-2.0"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "cpu_arch": ["native", "haswell"],
        "cuda_compute": "ANY"
    }
    default_options = {
        "shared": True,
        "fPIC": True,
        "cpu_arch": "haswell",
        "cuda_compute": "3.7"
    }
    requires = ["eigen/3.3.7"]

    @property
    def _source_subfolder(self):
        return os.path.join(self.source_folder, "source_subfolder")

    @property
    def _bazel_bin_folder(self):
        return os.path.join(self._source_subfolder, "bazel-bin", "tensorflow")

    @property
    def _is_debug_build(self):
        return self.settings.build_type in ["RelWithDebInfo", "Debug"]

    def config_options(self):
        if self.settings.os == 'Windows':
            del self.options.fPIC
            del self.options.cpu_arch
        if self.settings.build_type == "Debug":
            raise ConanInvalidConfiguration("Debug builds are not supported")
        if str(self.settings.compiler).lower() not in ("visual studio", "clang"):
            raise ConanInvalidConfiguration("Only visual studio and clang compilers supported")

    def source(self):
        # we use our custom branch here which has a patch for https://github.com/tensorflow/tensorflow/issues/41904
        # This is based on the v2.3.0 release
        git_access_token = os.getenv('GIT_ACCESS_TOKEN')
        if not git_access_token:
            self.output.warn('No Access Token Provided')

        fuel3d_repository = f"https://Fuel3D:{git_access_token}@dev.azure.com/fuel3d/Core%20Libraries/_git/tensorflow"
        git = tools.Git(folder=self._source_subfolder)
        git.clone(fuel3d_repository, "windows_cppapi_exports")

    @property 
    def _latest_vc_compiler_version(self):
        if self.settings.compiler != "Visual Studio":
            return "0"
        vs = tools.vswhere(latest=True)
        return tools.Version(vs[0]["installationVersion"])

    @property
    def _tf_compiler_vars(self):
        tf_vars = {}
        if self.settings.compiler == "clang":
            tf_vars["CC"] = tools.which("clang")
            tf_vars["CC_OPT_FLAGS"] = f"-march={self.options.cpu_arch}"

        elif self.settings.compiler == "Visual Studio":
            vs_version = self._latest_vc_compiler_version
            # Tensorflow uses flags in the latest patches to VS-2019 to reduce compilation time
            # We disable this option for now as it creates a 400Mb dll!
            use_large_function_opt = False
            if use_large_function_opt:
                tf_vars["TF_VC_VERSION"] = "{}.{}".format(vs_version.major, vs_version.minor)
                tf_vars["TF_OVERRIDE_EIGEN_STRONG_INLINE"] = "1" if vs_version < "16.4" else "0"
            else:
                tf_vars["TF_OVERRIDE_EIGEN_STRONG_INLINE"] = "1"
            tf_vars["CC_OPT_FLAGS"] = "/arch:AVX"

        return tf_vars

    @property
    def _bazel_build_args(self):
        tf_args = [
            "--config=opt",
            f"--jobs={tools.cpu_count()}"
        ]
        if not self._is_debug_build:
            tf_args += ["--strip=always"]
        if self.settings.compiler == "clang":
            tf_args += ["--config=nonccl"]
            if self.settings.compiler.libcxx == "libc++":
                tf_args += [
                    '--cxxopt=-stdlib=libc++',
                    '--linkopt=-stdlib=libc++'
                ]

        return tf_args

    @property
    def _cuda_config(self):
        return {
            "TF_NEED_CUDA": "1",
            "TF_NEED_TENSORRT": "1",
            "CLANG_CUDA_COMPILER_PATH": tools.which('clang'),
            "TF_CUDA_CLANG": "1",
            "TF_CUDA_COMPUTE_CAPABILITIES": str(self.options.cuda_compute),
            "TF_DOWNLOAD_CLANG": '0',
            "TF_CUDA_VERSION": "10.2"
        }

    @property
    def _linux_config(self):
        return {
            "PYTHON_BIN_PATH": sys.executable,
            "USE_DEFAULT_PYTHON_LIB_PATH": "1",
            "TF_ENABLE_XLA": "1",
            "TF_NEED_OPENCL_SYCL": "0",
            "TF_NEED_ROCM": "0",
            "TF_NEED_MPI": "0",
            "TF_SET_ANDROID_WORKSPACE": "0",
            "TF_CONFIGURE_IOS": "0"
        }

    @property
    def _windows_config(self):
        return {
            "PYTHON_BIN_PATH": sys.executable,
            "USE_DEFAULT_PYTHON_LIB_PATH": "1",
            "TF_ENABLE_XLA": "0",
            "TF_NEED_OPENCL_SYCL": "0",
            "TF_NEED_ROCM": "0",
            "TF_NEED_CUDA": "0",
            "TF_NEED_MPI": "0",
            "TF_DOWNLOAD_CLANG": "0",
            "TF_SET_ANDROID_WORKSPACE": "0",
            "TF_CONFIGURE_IOS": "0"
        }

    def build(self):
        with tools.chdir(self._source_subfolder):
            env_build = {}
            if self.settings.os == "Linux":
                env_build.update(self._linux_config)
                env_build.update(self._cuda_config)
            elif self.settings.os == "Windows":
                env_build.update(self._windows_config)
            else:
                raise ConanInvalidConfiguration("OS not supported")

            env_build.update(self._tf_compiler_vars)
            self.output.info("Tensorflow env: ")
            self.output.info(env_build)
            with tools.environment_append(env_build):
                self.run("python configure.py" if tools.os_info.is_windows else "./configure")
                command_args = self._bazel_build_args
                command_line = "bazel build " + " ".join(command_args) + " "
                self.output.info("Running tensorflow build: ")
                self.output.info(command_line)
                self.run(command_line + "%s --verbose_failures" % "//tensorflow:tensorflow_cc")
                self.run(command_line + "%s --verbose_failures" % "//tensorflow:tensorflow_cc_dll_import_lib")
                self.run(command_line + "%s --verbose_failures" % "//tensorflow:install_headers")

    def package(self):
        self.copy(pattern="LICENSE", dst="licenses", src=self._source_subfolder)
        if self.settings.os == "Windows":
            self.copy(pattern="tensorflow_cc.dll", dst="bin", src=self._bazel_bin_folder, keep_path=False, symlinks=True)
            self.copy(pattern="tensorflow_cc.lib", dst="lib", src=self._bazel_bin_folder, keep_path=False, symlinks=True)
        elif self.settings.os == "Linux":
            self.copy(pattern="libtensorflow_cc.so*", dst="lib", src=self._bazel_bin_folder, keep_path=False, symlinks=True)
            self.copy(pattern="libtensorflow_framework.so*", dst="lib", src=self._bazel_bin_folder, keep_path=False, symlinks=True)
            lib_name = "libtensorflow_cc.so"
            lib_folder = os.path.join(self.package_folder, "lib")
            v = tools.Version(self.version)
            os.symlink(f"{lib_name}.{self.version}", os.path.join(lib_folder, f"{lib_name}.{v.major}"))
            os.symlink(f"{lib_name}.{v.major}", os.path.join(lib_folder, lib_name))

        self.copy(pattern="*", dst="include", src=os.path.join(self._bazel_bin_folder, "include"), keep_path=True, symlinks=False)
        if self._is_debug_build:
            self.copy(pattern="tensorflow_cc.pdb", dst="bin", src=self._bazel_bin_folder, keep_path=False, symlinks=True)
        include_folder = os.path.join(self.package_folder, "include")
        # dont use tensorflow provided Eigen due to assorted linking errors
        tools.rmdir(os.path.join(include_folder, "Eigen"))
        tools.rmdir(os.path.join(include_folder, "unsupported"))

    def package_info(self):
        self.cpp_info.includedirs = ["include", "include/src"]
        libs = ["tensorflow_cc"]
        if self.settings.os == "Linux":
            libs.append("tensorflow_framework")

        self.cpp_info.libs = libs
