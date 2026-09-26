/*
 * Copyright 2026 Ckristian Duran
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

module \$_MUX4_ (
    output Y,
    input A,
    input B,
    input C,
    input D,
    input S,
    input T
    );
  MUX4X1H7L _TECHMAP_MUX4 (
      .Y(Y),
      .A(A),
      .B(B),
      .C(C),
      .D(D),
      .S0(S),
      .S1(T)
  );
endmodule
