# Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import unittest
import numpy as np
import paddle
import paddle.base as base
from tests.op_test import OpTest
from paddle.base.backward import append_backward
from paddle.base import Program, program_guard

paddle.enable_static()


class TestWhereOp(OpTest):
    def setUp(self):
        self.op_type = "where"
        self.place = paddle.CustomPlace("mlu", 0)
        self.__class__.use_custom_device = True
        self.python_api = paddle.where
        self.init_config()
        self.inputs = {"Condition": self.cond, "X": self.x, "Y": self.y}
        self.outputs = {"Out": np.where(self.cond, self.x, self.y)}

    def test_check_output(self):
        self.check_output_with_place(self.place)

    def test_check_grad(self):
        self.check_grad_with_place(self.place, ["X", "Y"], "Out")

    def init_config(self):
        self.x = np.random.uniform((-3), 5, 100).astype("float32")
        self.y = np.random.uniform((-3), 5, 100).astype("float32")
        self.cond = np.zeros(100).astype("bool")


class TestWhereOp2(TestWhereOp):
    def init_config(self):
        self.x = np.random.uniform((-5), 5, (60, 2)).astype("float32")
        self.y = np.random.uniform((-5), 5, (60, 2)).astype("float32")
        self.cond = np.ones((60, 2)).astype("bool")


class TestWhereOp3(TestWhereOp):
    def init_config(self):
        self.x = np.random.uniform((-3), 5, (20, 2, 4)).astype("float32")
        self.y = np.random.uniform((-3), 5, (20, 2, 4)).astype("float32")
        self.cond = np.array(np.random.randint(2, size=(20, 2, 4)), dtype=bool)


class TestWhereOp4(TestWhereOp):
    def init_config(self):
        self.x = np.random.uniform((-3), 5, (20, 2, 4)).astype("float16")
        self.y = np.random.uniform((-3), 5, (20, 2, 4)).astype("float16")
        self.cond = np.array(np.random.randint(2, size=(20, 2, 4)), dtype=bool)


class TestWhereAPI(unittest.TestCase):
    def setUp(self):
        self.place = paddle.CustomPlace("mlu", 0)
        self.__class__.use_custom_device = True
        self.init_data()

    def init_data(self):
        self.shape = [10, 15]
        self.cond = np.array(np.random.randint(2, size=self.shape), dtype=bool)
        self.x = np.random.uniform((-2), 3, self.shape).astype(np.float32)
        self.y = np.random.uniform((-2), 3, self.shape).astype(np.float32)
        self.out = np.where(self.cond, self.x, self.y)

    def ref_x_backward(self, dout):
        # flake8: noqa
        return np.where((self.cond == True), dout, 0)

    def ref_y_backward(self, dout):
        # flake8: noqa
        return np.where((self.cond == False), dout, 0)

    def test_api(self):
        for x_stop_gradient in [False, True]:
            for y_stop_gradient in [False, True]:
                train_prog = base.Program()
                startup = base.Program()
                with base.program_guard(train_prog, startup):
                    cond = paddle.static.data(
                        name="cond", shape=self.shape, dtype="bool"
                    )
                    x = paddle.static.data(name="x", shape=self.shape, dtype="float32")
                    y = paddle.static.data(name="y", shape=self.shape, dtype="float32")

                    x.stop_gradient = x_stop_gradient
                    y.stop_gradient = y_stop_gradient

                    result = paddle.where(cond, x, y)
                    result.stop_gradient = False
                    append_backward(paddle.mean(result))

                    exe = base.Executor(self.place)
                    exe.run(startup)

                    fetch_list = [result, result.grad_name]
                    if x_stop_gradient is False:
                        fetch_list.append(x.grad_name)
                    if y_stop_gradient is False:
                        fetch_list.append(y.grad_name)
                    out = exe.run(
                        train_prog,
                        feed={"cond": self.cond, "x": self.x, "y": self.y},
                        fetch_list=fetch_list,
                    )
                    assert np.array_equal(out[0], self.out)

                    if x_stop_gradient is False:
                        assert np.array_equal(out[2], self.ref_x_backward(out[1]))
                        if y.stop_gradient is False:
                            assert np.array_equal(out[3], self.ref_y_backward(out[1]))
                    elif y.stop_gradient is False:
                        assert np.array_equal(out[2], self.ref_y_backward(out[1]))

    def test_api_broadcast(self, use_mlu=True):
        main_program = Program()
        with base.program_guard(main_program):
            x = paddle.static.data(name="x", shape=[-1, 4, 1], dtype="float32")
            y = paddle.static.data(name="y", shape=[-1, 4, 2], dtype="float32")
            x_i = np.array([[0.9383, 0.1983, 3.2, 1.2]]).astype("float32")
            y_i = np.array([[1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0]]).astype(
                "float32"
            )
            result = paddle.where((x > 1), x=x, y=y)
            for use_mlu in [False, True]:
                place = paddle.CustomPlace("mlu", 0) if use_mlu else base.CPUPlace()
                exe = base.Executor(place)
                out = exe.run(
                    base.default_main_program(),
                    feed={"x": x_i, "y": y_i},
                    fetch_list=[result],
                )
                assert np.array_equal(out[0], np.where((x_i > 1), x_i, y_i))

    def __test_where_with_broadcast_static(self, cond_shape, x_shape, y_shape):
        paddle.enable_static()
        main_program = Program()
        with base.program_guard(main_program):
            cond = paddle.static.data(name="cond", shape=cond_shape, dtype="bool")
            x = paddle.static.data(name="x", shape=x_shape, dtype="float32")
            y = paddle.static.data(name="y", shape=y_shape, dtype="float32")
            cond_data_tmp = np.random.random(size=cond_shape).astype("float32")
            cond_data = cond_data_tmp < 0.3
            x_data = np.random.random(size=x_shape).astype("float32")
            y_data = np.random.random(size=y_shape).astype("float32")
            result = paddle.where(condition=cond, x=x, y=y)
            for use_mlu in [False, True]:
                place = paddle.CustomPlace("mlu", 0) if use_mlu else base.CPUPlace()
                exe = base.Executor(place)
                out = exe.run(
                    base.default_main_program(),
                    feed={"cond": cond_data, "x": x_data, "y": y_data},
                    fetch_list=[result],
                )
                expect = np.where(cond_data, x_data, y_data)
                assert np.array_equal(out[0], expect)

    def test_static_api_broadcast_1(self):
        cond_shape = [2, 4]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)

    def test_static_api_broadcast_2(self):
        cond_shape = [2, 1]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)

    def test_static_api_broadcast_3(self):
        cond_shape = [2, 2, 1]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)

    def test_static_api_broadcast_4(self):
        cond_shape = [2, 1, 4]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)

    def test_static_api_broadcast_5(self):
        cond_shape = [3, 2, 2, 4]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)

    def test_static_api_broadcast_6(self):
        cond_shape = [2, 2, 4]
        a_shape = [2, 2, 1]
        b_shape = [2, 2, 1]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)

    def test_static_api_broadcast_7(self):
        cond_shape = [2, 2, 4]
        a_shape = [2, 1, 4]
        b_shape = [2, 1, 4]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)

    def test_static_api_broadcast_8(self):
        cond_shape = [3, 2, 2, 4]
        a_shape = [2, 2, 1]
        b_shape = [2, 2, 1]
        self.__test_where_with_broadcast_static(cond_shape, a_shape, b_shape)


class TestWhereDygraphAPI(unittest.TestCase):
    def test_api(self):
        with base.dygraph.guard(paddle.CustomPlace("mlu", 0)):
            x_i = np.array([0.9383, 0.1983, 3.2, 1.2]).astype("float32")
            y_i = np.array([1.0, 1.0, 1.0, 1.0]).astype("float32")
            cond_i = np.array([False, False, True, True]).astype("bool")
            x = base.dygraph.to_variable(x_i)
            y = base.dygraph.to_variable(y_i)
            cond = base.dygraph.to_variable(cond_i)
            out = paddle.where(cond, x, y)
            assert np.array_equal(out.numpy(), np.where(cond_i, x_i, y_i))

    def __test_where_with_broadcast_dygraph(self, cond_shape, a_shape, b_shape):
        with base.dygraph.guard(paddle.CustomPlace("mlu", 0)):
            cond_tmp = paddle.rand(cond_shape)
            cond = cond_tmp < 0.3
            a = paddle.rand(a_shape)
            b = paddle.rand(b_shape)
            result = paddle.where(cond, a, b)
            result = result.numpy()
            expect = np.where(cond, a, b)
            np.testing.assert_array_equal(expect, result)

    def test_dygraph_api_broadcast_1(self):
        cond_shape = [2, 4]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)

    def test_dygraph_api_broadcast_2(self):
        cond_shape = [2, 1]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)

    def test_dygraph_api_broadcast_3(self):
        cond_shape = [2, 2, 1]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)

    def test_dygraph_api_broadcast_4(self):
        cond_shape = [2, 1, 4]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)

    def test_dygraph_api_broadcast_5(self):
        cond_shape = [3, 2, 2, 4]
        a_shape = [2, 2, 4]
        b_shape = [2, 2, 4]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)

    def test_dygraph_api_broadcast_6(self):
        cond_shape = [2, 2, 4]
        a_shape = [2, 2, 1]
        b_shape = [2, 2, 1]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)

    def test_dygraph_api_broadcast_7(self):
        cond_shape = [2, 2, 4]
        a_shape = [2, 1, 4]
        b_shape = [2, 1, 4]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)

    def test_dygraph_api_broadcast_8(self):
        cond_shape = [3, 2, 2, 4]
        a_shape = [2, 2, 1]
        b_shape = [2, 2, 1]
        self.__test_where_with_broadcast_dygraph(cond_shape, a_shape, b_shape)


class TestWhereOpError(unittest.TestCase):
    def test_errors(self):
        with program_guard(Program(), Program()):
            x_i = np.array([0.9383, 0.1983, 3.2, 1.2]).astype("float32")
            y_i = np.array([1.0, 1.0, 1.0, 1.0]).astype("float32")
            cond_i = np.array([False, False, True, True]).astype("bool")

            def test_Variable():
                paddle.where(cond_i, x_i, y_i)

            self.assertRaises(TypeError, test_Variable)

            def test_type():
                x = paddle.static.data(name="x", shape=[-1, 4], dtype="bool")
                y = paddle.static.data(name="y", shape=[-1, 4], dtype="float16")
                cond = paddle.static.data(name="cond", shape=[-1, 4], dtype="int32")
                paddle.where(cond, x, y)

            self.assertRaises(TypeError, test_type)

    def test_value_error(self):
        with base.dygraph.guard(paddle.CustomPlace("mlu", 0)):
            cond_shape = [2, 2, 4]
            cond_tmp = paddle.rand(cond_shape)
            cond = cond_tmp < 0.3
            a = paddle.rand(cond_shape)
            self.assertRaises(ValueError, paddle.where, cond, a)


if __name__ == "__main__":
    unittest.main()
