#include "tensorflow/cc/ops/standard_ops.h"
#include "tensorflow/core/framework/graph.pb.h"
#include "tensorflow/core/public/session.h"
#include "tensorflow/core/framework/tensor.h"

#include <iostream>

namespace tf = tensorflow;
using namespace tf::ops;

int main(int argc, char** argv)
{
  tf::Scope root = tf::Scope::NewRootScope();
  auto a = Const<float>(root, {{3, 2}, {-1, 0}});
  auto x = Const(root.WithOpName("x"), {{1.0F}, {1.0F}});
  auto y = MatMul(root.WithOpName("y"), a, x);
  auto y2 = Square(root, y);

  auto y2_sum = Sum(root, y2, 0);
  auto y_norm = Sqrt(root, y2_sum);
  Div(root.WithOpName("y_normalized"), y, y_norm);

  tf::GraphDef graph;
  root.ToGraphDef(&graph);

  std::unique_ptr<tensorflow::Session> session(tensorflow::NewSession({}));
  tensorflow::Status s = session->Create(graph);

  tf::Tensor x_in(tf::DT_FLOAT, tf::TensorShape({2, 1}));
  auto x_flat = x_in.flat<float>();
  x_flat.setRandom();
  auto inv_norm = x_flat.square().sum().sqrt().inverse().eval();
  x_flat = x_flat * inv_norm;

  std::vector<tensorflow::Tensor> outputs;
  s = session->Run({{"x", x_in}}, {"y:0", "y_normalized:0"}, {}, &outputs);

  auto y_out = outputs[0].flat<float>();
  auto yn_out = outputs[1].flat<float>();

  std::cout << "y: [" << y_out(0) << "," << y_out(1) << "]\n";
  std::cout << "y_normalized: [" << yn_out(0) << "," << yn_out(1) << "]\n";

  // Close the session.
  session->Close();

  return 0;
}


