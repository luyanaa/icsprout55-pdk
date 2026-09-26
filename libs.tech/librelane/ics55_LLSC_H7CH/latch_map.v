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

module \$_DLATCH_P_ (input E, input D, output Q);
  LATHX1H7H _TECHMAP_DLATCH_P (
    .D(D),
    .Q(Q),
    .G(E),
    .QN()
  );
endmodule

module \$_DLATCH_N_ (input E, input D, output Q);
  LATLX1H7H _TECHMAP_DLATCH_N (
    .D(D),
    .Q(Q),
    .GN(E),
    .QN()
  );
endmodule

module \$_DLATCH_NN0_ (input E, input R, input D, output Q);
  LATLRX1H7H _TECHMAP_DLATCH_NN0 (
    .D(D),
    .Q(Q),
    .GN(E),
    .RN(R),
    .QN()
  );
endmodule

module \$_DLATCH_PN0_ (input E, input R, input D, output Q);
  LATHRX1H7H _TECHMAP_DLATCH_PN0 (
    .D(D),
    .Q(Q),
    .G(E),
    .RN(R),
    .QN()
  );
endmodule

module \$_DLATCHSR_NNN_ (input E, input S, input R, input D, output Q);
  LATLSRX1H7H _TECHMAP_DLATCHSR_NNN (
    .D(D),
    .Q(Q),
    .GN(E),
    .SN(S),
    .RN(R),
    .QN()
  );
endmodule

module \$_DLATCHSR_PNN_ (input E, input S, input R, input D, output Q);
  LATHSRX1H7H _TECHMAP_DLATCHSR_PNN (
    .D(D),
    .Q(Q),
    .G(E),
    .SN(S),
    .RN(R),
    .QN()
  );
endmodule
