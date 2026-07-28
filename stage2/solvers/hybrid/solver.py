"""
hybrid - dual-track solver for the SAIR Equational Theories Stage 2 challenge.

One file, both tracks. It runs in Marathon when JUDGE_MARATHON_MANIFEST is set
and in Solo otherwise, so the same submission can be entered on either track.

Design principle: prove what can be proven deterministically, and only then
ask the model. A finite magma counterexample is checked exhaustively in
Python before it is emitted, so every `false` certificate is correct by
construction and the Lean judge's `decideFin!` only confirms it. That
reliability is the point: model-written Lean proofs fail often, deterministic
certificates do not. This matters most in Marathon, where the judge gives no
per-answer feedback, so a guessed proof cannot be retried.

Order of attack (both tracks):
  0. Verdict lookup in the embedded Equational Theories Project table, which
     settled the full implication matrix for these laws. The verdict steers
     the budget to the right certificate type; it is never emitted without a
     locally verified certificate.
  1. Counterexample search on finite magmas (Fin 2, 3 exhaustive; Fin 4 by
     constrained backtracking). Verified in Python. Clears most `false`
     problems with no tokens.
  2. Collapse proof: if the hypothesis forces every element equal, any goal
     follows. Clears the degenerate `true` problems with no tokens.
  3. Model fallback for the `true` problems that need a real proof. In Solo
     the judge error is fed back each round; in Marathon a single guarded
     attempt is made per unsolved problem while the token budget allows.

Lean templates match the judge contract exactly:
  true  : Goal = forall (G : Type) [Magma G], EquationLHS G -> EquationRHS G
  false : Goal = exists (G : Type) (_ : Magma G), EquationLHS G and not EquationRHS G
"""

PROMPT = """You are a Lean 4 proof engineer working on magma equational implications.

Hypothesis h ({problem.equation1_id}): {problem.equation1}
Goal      ({problem.equation2_id}): {problem.equation2}

{solver.analysis}

Previous attempts and judge errors:
{history.attempts}

The magma operator is written as the character U+25C7. Never write it as *.
The proof body runs after `intro G _ h`, so `h` is the hypothesis, universally
quantified over its variables. Derive the goal from `h`.

Do not write the intro line for the goal variables; it is added
automatically. Begin directly with the proof steps.

Use only these tactics: exact, have, calc, rw, congr_arg, .symm, .trans.
Never use: sorry, admit, decide, simp, simpa, aesop, omega, linarith,
tauto, ring, norm_num. Never claim a non-trivial equation by rfl.

The MATCH then COLLAPSE method solves almost all of these:
  MATCH:   instantiate h with compound arguments so its shape lines up with
           the goal's outer structure.
  COLLAPSE: use that free variables in h can take any value to rewrite the
           leftover inner terms into what the goal needs.

Respond with ONLY JSON, no markdown:
{"verdict": "true", "proof": "<tactic body, no theorem statement>"}
or
{"verdict": "false", "counterexample_table": [[0,1],[1,0]]}
"""


import json
import os
import random
import re
import sys
import time
from itertools import product


OP = "◇"  # the magma operator, U+25C7


# -- ETP verdict table -----------------------------------------------------
# The Equational Theories Project settled the full 4694 x 4694 implication
# matrix. The equations collapse to 1415 equivalence classes, so the whole
# table fits here as a class map plus a 2 bit class matrix, zlib compressed.
# The verdict steers budget only: every certificate is still constructed and
# verified before it ships, so a lookup miss can never produce a wrong
# answer. Codes: 0 unknown, 1 true, 2 false, 3 conjectured false.

_ETP_N = 4694
_ETP_BLOB = b"c-rlK3Bc?~RqoCF12V{u!-XGNWKk419y;KTJP`#(pHCRD`?td~aIqsf&xb3Z2m&hVbsG>nl5$5<a&qNzk!AFXECZ;x;l3;Gzy)P<f4=9ds%(|5J4vUylk~~V{X6MSrz<C?zB+a4obQ~mt~$EfvTk+j54+9LHMg}s+_J8*EbDg1xBrOaYj11a!Lr1M*4aDW>E!I4Pwsf~k$1W4-EMvNk2<=?J&*2nbaZs@kG4MMKGwa(86W#`)_pCtSNvyv{3m?kCw=n${@eXO<x{Wwum>C+UGqTe(>`7O$Y*?}^;yx+$$y`1W&76WJm_<ej~{$|{NF$CA)kMIeEiTa_`+-M6McFg{X6>itcM*x{1M03f6?(5f8O!!A98&BKfc8JpI>S{Qhe~J8>~l1_wg9<@5{u$nH3#d^V2V1oZ62)eca<upKyA5dgBwVC!JHDJo!G>S48Jr8=sr}vzE?RKE;Lq^;Q4-sbBpyU;EUrI{S5Jzy2GZcJ}FK&pzWDPrm7yCnw_nlW#tWUXy>%diJ+G=ef`O)^Gdv=Rf~DzVo}j?fiG2|DNytzVqLI{`^fZIC;h$PlRMoPF{Ety(a&D;6*>Ux{LQiFZS83fB4q7zV(m%=#TyQPaOT^OMdF;rNI&Z>7$q7ZH_|m3@#k~%u)FABej2Y@fFskS6UZED}VM?)~jD5_Fk)wE?T#>F5YaZee36b-n#q?V)u2{FTUP-gB71}vwHnGD?TZD^NrTUH>GdfqITY#o^f+_dis^hKh|5``b)q3D{uSNU;Fjn_|3b%{noest=~TSo!>qBJ<;CZ|AV7H{G+2k{*ymd>hxzve}42A?>JKXNB90q>#zP=Y0%&Nt@U?*FZOO$NAI-WW!?MTv2I;?kM-VvP#^u{`>gjzZ+<`=eNeo9C{e&j6UDb~N#BSr^-t*;;*)>Yb+-18^)LVWZ~y)Y|M7qR^Z)+8|2kuR@+XVVBfHKux4r*|%RY1M9j?30b$35HdvwR6+Z^5LB)OG4TOWBB_5Hiv&AR(XiM@NoKXp&*-uFr_|IyaRevH_Copqm&O>X7h;sMClf7aXZan_rxd%rP$<G$kHgSlJz`0UO%+=}d%w^kkVlRxpg2Ym7aKkd^$<1>#w>$5-S=s}-*^kCWZ9(wczUwCx%VGn!w(IajnUPb3Uy5@T8i@sR(x2S(zBYK!TdX#m8b<LyWp7@wAvu1O#duo08`>aLMRd2Cu@%q@LyGGx7oF%T9ym7Pjc=7s#^bDb3H|nUM{yfUc9jZUp6Q6YM$zPG{m|rJ4<<swf|7U#TH$C&4W$(N0e$Tz;{-Osy;KROM+{*Lit$c^|o!_OtfBw6z@A+Q!`w^hrqJCOk`TM@#y6FY#qZj^w^`fLL_f)9!gL)fQ@>}mp-|(y-60a{#&$x$W`K4R=?5bN~Kl~#<`k){C@#CNP$>Wy@==-Uc2K=XAhT-w?g)jP<mtTCvrH8!oAwMhLf7S7;k6-gz`6{-Xf9~fm|HA8j@%3-`!Z*Ijy5-H{`MxDqfZJLhxH*2_Z~Z0fmw!d<zRmj8U&|CM(!@evxvh2Io6|S$neQvV?nV0e!OaTx8^8JX-}>#}`Q6|9{XaPV+&?@%{-ZxW{*ymF{xi|uKmUt&{N-Q$_22yM-@W7S#nC&D-*x=%E62wY>5t#@Uh5zJ(R!cw_WM6zeegr#cW+id_b;LYU-Rx*NdNk8*1!LU^?$7YwEpk^v;Hf3^NjWJN;m#h7pGKD0sqMxZ&W)Uo}Te0)lBuZ!ec0CnH(f<b*wu2@rNJZ?pSs8cbq-G<MEwNj_>@D@3_nHt&Si3vhetC-tiIdc;{W?Te;iat&h5g`u;udCA;@EVi@|EVxvT7|G4{#-Pc(k|Dmj}M4Ff=zx4@8>)#Z=@rgnjcCN3yJL+1GFW*Yxek?f{pWgpdPCxa!2Ru-Wd9v4wPA~Qz^tr0npFZ^T3&hbEo<8jK;g687V!Qr}zF78m@$D~tr1fc!5?8uM+7)iNSA6A1KjzDlZvW=2ue?RQCdzL;^!2a%!haG9_AfW5&AYAY2rt&Vz3f^)RC6m?udx=#_G6D9_xR%{+<5$OA@C<Y>G<4}kH2DheC&MX@l!4y-~JV^J$8jD01tWf@&9_|u`&yezv_QmPyK4^Ys9y|_Uo*#{|4)6;ufARj-FxN%lbyqO{K+PebY0oZ+?N;z1e!!v#oE52L9)Wqvwj(=Ou=~w~Bw?Cc6E%zbpRM^Tok;h}Z8-&iF2IE9b@QcPDRrkNoq!R&0hSJ0$wR`o81uzv=h|FFgK%7ajkgXywW~{-GBi`|mhDW<PxVBY$=Lqknzn_<C`4`@enH@sItTcoqA{KmIuDCw|g;iTL(Uz0?Z0xY8}wPm80MiI!e{b9`kCtqVV6y<CjMuefBrGJ5l8g)Y5HyuLd5d1>Ul#=73R`f>3auNC9U&9Ob8-gt}{SA;ca{e1dHdKXvc|5%q#f8lkfzxevoH@xxm%Rl?{^i8*%zIk!_mbads{?ad>{>tZ_zU?88IQ><jQ@<t@?AIT9stm8w-}p`I?Z0LHw)pn%{I2zTzi<74kmw((E8bxJQEa_gfBYxbpZ=Nk=c3#H#XGFOOia3asMk9rKmR|(zo&_B{naDmr}Ee00nhX^{zf3!--_42%iT(L1KLyh`_p&6>-61MPT%uh(aZ;*{=+|>zVH2~9}w;R;D=8C>GMwiS@aeAUrtZ|^&t;C{kKQNw<3}0Kh^goILW7Svj8Vcy<UAwa^<TmVRp;6Zgp$x!xBsLX7zfT<mazZJMYTAbz5;D(d%}}8ONgA-(ELPudR3>(GLp1I(zLM?{w|Sov;1KYp=cbE_c25Zg;=-qr~1l?s@IK?k(Osd+kSyqmQ}vKG%Ni*=yA~*9v6%_)idEBSFKu-+xo>y}!EREt!IS%BNb_J-~XPcq+oK|BU2TJ~RJRB$R!Ycpg{ZkTx{x_MelsTwL!#&2A;aDKRN{*ux)j{Zk|~{m(Cb<fCqQssbQk(c7o9$KLR`M?e0lPk7{wPkic^Jn4qVJ@wIN&z*hpSDZb&JbN~^5}tPUtIvvezUJ)NuRW_iIs0{AfAS4aJ2`p!Gfuwon@*njbg?IG`DdxuXUTo}PZ{@5fA-1Ax1?`8N9{a2J>$72C(la`(yv5&g+FpiAZ7&Tzgx@)zW=5dyigkb%I5!JY45-2Cw}rJKl)QIekl_+fcLT=f6<HZ#V_^Q+3@UzpLzM&i)YWi;?gUB_EoQb&1-M|xwAii_N*`gE}#8HaT~7}|K9M%lQ-QWCLhl_dGlLN-WpF!e(722^%=>u<m8vdzh8OV$;q!KZ~WS?tDWCS&-l%gleg<LnUmi-N%jhVqLKa&|43N#f0hpLfB(*Rz5B|0-un-Cdhb8J_fGG9-#g#`?hm}{PJj2o554QJ|LL9Yf7iRu|MPiaP@n(z^XC(j`l_SzSD!yGZ0cK`zs>pc=dTg}Zu{XUw>v&Lx&23+JmcDvJH)qg_KxZ`ZQIG6<R9@=?krwzFZVz4+3J($q-Wga<m9foTe(}^t=#>i?s3n1-TR|I<~|?$arf1xuMbcr@@L)evp?rSpYgfZJ@|n_3qR%aKkI(?d+2o!e!v6If5Ca7kLMq8{`~c+MxKAPX#Qiq?ELwec%6%Xr(b@uuuo1N`}UK^J^thg@x<@OC#u(HBon`rCy9UOo_uoh72@@=@{OgVK6zGp##d?w>W!zIBzuKFd4o7Lhvj7S`C>LI{(t^=Jm))~Cp7TcLIt1s{m=Q%=RWVI7u@v1AGqnJ7u|G|Qby17nRn9<-z47ok(+M%(VNsKH~rX;pZvs6iXVC2$xD9f<fZYg1kWxsl*=9Q=1(VYyzGvJGf=y8^~MY9ZY8{+4B$xRFNHV%+{=a4`|{WQ;-%NW>J4vv)1_P9{FX~%o_Xn&ue$W=x7>2+SKfBv<-hv!U;Fh-uYS#MT>8zoUV8J}UvcTxmtOPsOK-dUGcW(GOK*6sIJ$K4(xq3w_R`ya`{kEk{yUd`R~%gWy-RPnbm`5P-YRzU%KT@VHvi-M-v5CQe(0b6`F%op-}j+^|Bv?x<^AA?{@=g-*Za;`>5MR*5T3o=9dCDs+uiBp&bJfJlaILec6T_r-QCLibzh-i_x+?#z3#q3$3F3sKK;7;-B(#<u}Svd1=fAO1Usc!5C78ZANlY{-EjTG9{rf>zwCzD^<VTQ^DlYi^{3*E>%aWr*FW-xh4^#5{c!RAW4~B@@TiC1aQ)*R|AZUUInueuxp1S<iW{H$)#tuuDHP+J(2R5Ep7D+6p1eHgJpCKaebX}^f8#gbDAdIH%IBPW?zwYMd)|}IIp@CedFP(_RZqC_TfgONpCXRVJ@MQ*=PBo&`E56T)s5f&EzcJR=f30I*NSt`$=x%w(MDUBP0VD^Sjm>`MW39p;?K_{$5!$cwP&RtWV`8p_Py$#tv#rDr@sA3v*U)v$LT@RSWCNT&8=94TZuoia_zCot<RrObw;E6v#K}!`NVgn{YL3ls-LlTQoarA8fq18#cKRutn>-QN|d%gc|vCr*`_L^Yhhl&DsClzv(`o>v&vfELcy}uSKO3k>9?Y_(#r3ZgdKlmX;0;<lFak^TC-hMBdp?SVpD&_-!t)^744mg_mWmwSEb*P|Lc3!nX8J8(oV9<ZPyxE+3J!CTAM*5zLn@TI?V5>n~85T{_W(0GwE9yf?Z{47mmNVrmt95bweB9N=^*Pt!T1TEmUogzjalt8dv27ewDUYbCQ+rWir1?e;6I#C_l}@t!QntlBQghB3Il>E7F+U>1T>Rr{C{Y>ux3KK&jBnXIM3=xc;eJl}IpoDoXEi3byvCoT++rmUb(ZdXj&Z#WR#t+uzEWisy4Cxy910<oAw>7d|?Y|0jEe&q_P`8%M=6j+%k-QKv0wp4Q&#TR9R^)^DYvRY%29u+;i4w{oUpPk$r+b0)fhBkkK~k~_=f8lQBO?qw$&rL8S~tMZJa+_S3x)9IO<iT<9+y_ei*?pDqm=})Ef2=!a3J>%$1qi3{9kJ9IJrv6s07TcMt&zwnKqkmV+|D%8EjWf}k`PQg2kItmuQU}E|uFkdi>bhIGy2B>hmNh<oFKKuFR*ueGz3Eo2)^DZajH9h@CA#d@o$faKe*RV}WUdacKC|X#8+QAvN3h+BHo0L)o6!wsw3*#jZpgxrhta<fLx^6~E0dpz16|LV{(NdbC>-TZgqlyV<`k&DPPWUde-=x>%!?P~ymSd({#jO1%aWq<dL4Ea!Q2gJGZg=3LZesqOeuC~uf$6@4?=qu>-kE3VICcz-T_wH2hk_#QS@1IqWZ|z4<J1WwC~&5h2jIP#|6dRS++Y*nhDxfwJ*$)3u1cZReXu)dtv#k_(Kr?<Qwyl*>X3!>^%7u%>CFLr2s=)Xs5q){3SS!zu<1@uU4M7a26|n;Vc>V{e{nc=C6Fm<^F>C=sVzZ@g43v4)bR#@iBLq<2s@1`7SV*yWnt_&*tKNU=HJ4T-#ZS3o?f<#If%%dF8;h#c$3WM_gO{j`$_9=ejm?eAn~%O1v}km-FR9-krbnW}-ok5TE?g(p!i(#ICnoig(qUOHaHjK9kLnEfSx}KcbQ1n5&kF>odpm7Yo?{bQzm_OWB~M=g-8=Gx;X>=c4(xxRkhdbe8zmf-fCsE|2Bqfyw)lABh|F)r+{k_!03Nh%SiVn$P6*#LtD|jj+K;#~T59w{d{?JF0ZNGOI^~Z8zp3Q#u`b@-PSiV;IH^h7;9~`%ZQ+)9%6!^y}LBpPA`W$UW0wmF{V$_*i|uc8*&mN_&-kEhv5?g<&kgu#=%CuY+OCJxAVDPdH1yD0+XjhH>B__cuN(M|CpMPog8$k3?75q;x!FPJarcUCM2vjhKo^C>)fOnHPu5R+rxVMaFX~qkZ5=`Nt0%LA0TDAFI7~w=KI8tADuJEhi^Is<9v?S*?-S5x0Cl5{u9`aF#((&@h*aaf&aPD@F|m#IRR;B}Wbb(a7Mg6w)h=W?~Rq<QgYN3&&-i8rv3P%yh+2=!n6~v6&|a!yxD^afrq_F?24)80-hW(-bT9;ZO{k{&Jy)YH{~sbad6YD~{#08E*ja;ygKsf*AIMh?{mH7Foy$(UXDFSfK#NRy~cS4_)asau%xr7gyo&!{yOAn7lxuVQzM$v?@?nFKQG@P+(HyAhG0Gs%Ttx_o&my?+K_&T3-o<(ZlfKi+hlw1B)B08Ok~987s6~v$)x2<%f7mB7Xzd+XNW3XYEB<^7|1!ux+|vxe+{>E`b`S8`=|?HVBh8;u?FS6%6-vZ|2N1zKxa0I-8SxOZ?4#6js@_<}*x8F)>A%2Ym@Op5JK`Fl`E^P2N)5E}LOR2kTm5=jVsnj1uEltqm>iC~ZPKwTmZd!Uo(d@nrV53Rwc4B|{WKQ_3yPvklM>a*7wE2V#ziYYnvYdaR^(zHYT(E8R=ZX3)CZL9Q$C9ixOa&r(YYlxeiK1q@)*u+3PV2tY##L~PYemd;8X)?LEBxV_jmh^BBH<oyFgppQJB)>T;MVSaqaya$YHCT7U=-{pw~Dlf&-&zWX=<m`JM*$P~p!`1iY7rA`p0rwnvC2?fu$8?sNKdHG6`SA=iYb9i56F|0w#p7mf`oT7i1gOLCu1C5|4y@7WjB-+wSb8k7!yq@7CBr|jvn`^%>=~w3R(`TkZCyaP$v9d!z_PlbQn)R{+2|HO>~vU5#=e42a*I0>my;vEjSVak;h~WN6oVq)Fx?i@8F0MmFY`pRH{n;ceX%QipbKvmP4a{%)A2nq?yjOqnj5;%1jE(rPl6YQ;qL9>J#Ruv1zc@0Cuuv<shvuzS6gL5T5;TBi7q@q9o}*-8W|v%m?c<R+tYpdu@y-YHi_`kjK$O<iH*+0WK<S%Zsj7VTg1RMm}S>G8LF3Vyqfb_)h<-Gj@3FPGHrv>C7_8@g17LCL?1D1<9#KyY;P9xgF*=icMsjQvvpqej^4>&vKY>Ko4<xV&6?4`BKTxFOzn&t*1yB2EE?<;hRIqp48y*U^&j(sn}Um=Bqv!}meX_=gcFBhzGYVc8L;Np7|SAHEy%x96R@_nwR*tX0J{sc3s`I7_s9a)B(Sob+5_oNUC^`xy5k{hx`N8OH4}P)VZvd<)^KXH?ZF_Q_=ZXJ3O4MZSh+s8v8Uh|=6JYqs@2^Z4#S@p|1L+^c;O;x-rDU#wtKlT3=<9;k8L6e8-ih88Ij)17|J<~aj(vmawAwLR~z(?@M+WnZkfK}FiPL33`tJ2=&)H99j}ZkDaMr);+wE0!l_vnUFA6qv*_HtXVKa6(^(W`DUrgCuV5#UGLYnmg-PflYKyun{R8c~`IT!}g_TJx;uANhKq*@fS+^Ztkt+kNO6=Ot+L(mY6i>9Z5Vlg_ppPZF@}gMThV`<#i6Qn3??CgGLRTPL!o<cP>49@Qs2%{A=t4DlSTd+B!3^fhaHJ%A#Gb9VfDPB))Bs;}_x>KOcB%TsTF7qHT@|A!Ipp038DMlAl6mEzMVkTh5opF?2!`D>T*SsTd3{i2CeFnOjCP!yuY#bt78I+XVq+hwyLPwR(Z>J!WH+~TQf6qfT2+ItFq~X^4s%@7qRR07nY0(?vjm1^o}!%u@CvM3&1cJ?LFy*!ZPKA#sXmoJH}eoH;<usCxhLOewpVAv2Sy6R`;{=8cBDi$OTno}K<qe(BFoU>Rbf@E`2|^1g@n!2KE3n<?1YuPZx36#M8_}<iDER>?eRJ0SF3%Jo<XOC@X|oQd4E3V$ix&`n#^y~VHN!cm&60X9y|wO$m1k_l+$J(7hB6Ua`P}FVQ{q7xsAb)gkiO}K8nLKJ9ZLG<}hx4#c`;C_PftA;5=-SySj(XH!_Vv!ePTO95W8lW(tOF8$A<1CYMg21?!6l{qBj_PNxmrE@_xmq!G4<VJE<yB)?0BwU|v%F|73;_`%t>ek2WsUF;8r_h=8t6oYIZHo3uwy&??LjKeSt*RLXN4Z{%-t~p22WrgxjpKY+K7ME*gxS_@i$jqgkk`5bQRDdB!7<`<PHOzAwoy?k<v3Vogymrf4tt??vE&}YPdwg3M#vRX^TN7O(XQL*%40kYV<^;o`q1a2>cu~L1$6m7T=R=%X#u^(xgMi_p$gzDRNbOr$!z3;P)IMR#nF+CsNz6T^;qY9=3Y9Do+4{^_SeUT4oek|0^?L-xfVWtonCRM~tie2)3<>@ULEp@B6%_pJdZkDb;9)6NI}HwvBW<c%qebboADUQ^VJ*xttSJw?#<0d3)$YRF!^Qfst&(94Dp@jkm?uSGrF<t|Tj;9;!y1}nSksz<LtIG=M;x$LC31q`u+K$xwa^<cfs1e#L9ZgXazzQXC|;QrQ?)qD*FDIs7iV@zMCpx%PJ}wXshKb&fR9d!2@sQy$ARcfmPA3(AX$ZsMI~7P1hb1ck9o{yD6S+wKwfaL<fl(OX%H(j%VErWu34&a08k9sd6I5uVDg4_n7|j@Fc}ipfVBp{M0uTXfwFAfYQdCKLOk|R&<TNH%Ly0;dZV+7G_0zR=F$c<TxY2ms?AfLOG#{7y#VTI-_bMe`DsA=E)*JUp(-ed^LdW;U1%>lfRIb_9X#zjdEgDZ5ut*4IxY#i2fAzAbWW)xXqc;1v$-T__n^DDB<SXowUVG%mrprJdreCtw@1?Xpq6<a_tBeJb04$Q>~{7<^vgH65yud>=8nXR&DY1w&}L@#$7;)BhJ#s+VdI8j(qY4^If5N`n9hl%@M5l#U1#Cd-wqDRDUoG>LQ-Kg@m})Me1|vV&*r6K(VHSApw6OTg|k_47bE{gh+&meq6{IdJfLGG&18HzzF94?WxfMj;{x8^oyYad#@D_wVTQFD84L&@aMYRPQQI#@|E@&Jbb*%W)^B=;yV%hhp0tG75UgR+Ve{o`kgD&P?JzJ(3EQi|)jQ!0*x*LAIaO63_A6mrN6a<8&E<SxI$V!ivoT5-O6w!@t=2RumMld05%vSaqa5iNL^Ei<nNg&D#0~Zg!=scihl)N5Ra(V&g%Y)undh_F2&+e><$43H+<5+-2sqjoM7CQMQidkhFpkk0h6XdXt~Z9AtzlNl202E42~llcxFh*`djeR1zQ@|aFiTi5Su6DAb&zB`_6Q|BU(I1DS*C-vk3m$g51f`N36AaZr40=c95*VyAmG6<7MgZt`9UWQwiXrPxCn7%E)R0ICL#*wUb~X_ZEDdK@VF9-7v2aZ3|=7hjLo?&O(|g=5?qfvHt?1+J=;?c3FfmN0@g<By&T{Y9bea095Yi9mQ1Dn+z#%6DP%Xd!?sLjHttLf!f<@Hgcc?`k0uy;Ntx~36TF*Cw;qPMR<33|FzhA_gbTsY6x$YQ_=k84w~}xdcP_6}WEOD^jI2H=FHY{Dg5H6xGg+~ePo~Wnq7OZ$r7|ECi6hbwe3gR2*TV4la2T5m<9wIEykUvX9rY3&tC2A_!b<EX;-%J$Cs$s4f8{dt7vZR2SpF}9+2kKlE!>xr4OyPaRxm7XDOkj%#Fq<ENt`Vlf3b=yiHqtXOEE!N`b%dqkIoX`@|QC8cNP^47r-fskVh8~=lk--Q*%aH0!q9se`^+3BA2;me2pI)#<z;Z;{q@$MG3LmwUZEJV-&qBl9`w7Xt4YA#vzfcnhh<0NlLhx*L|BcN@$GJ3=bvaxP*sWtx-bbuE6nN1J)R4y+|0%^_0PG<+XjN$a&l<0$>(R*5?^*#iUmAdn_9pc8qO-#xOiZ2}2nlc^NNZD{}(EjZ1W6Ud<01uE+=F_5WGLx_t-ZZQgj%|A5)RoULpr*t|p+Tf<YdhiATozj@GPjGto{7ZFImIy8b|_b}{XCv{4o?v;t064<5qYu+ib28O|#o`mg{bmit4Go+7RN?60hsBA2(=3VB{9$Wdi1kTn3tVP?B2h)@Ae5tzeYGYUnTj65m1RWeSz8m<S>n1!)yat8lfqc$mvL&*(;d#85%^K#Z@i0rsQ_`W{PQPcD&x$|P;)caxyxs@NudH%Yl!QZN6*9JYc8Le&MB}Yz4BPqV_!K3~8hH#@PfpARzF{QaFdFp@+c;g{a15Ut&Vtq>5oF;e4Sd5s9+Gd^kxO)#%MN2p+vy--zd^v-_*U~9@zk<LSh=SBa<|INEwekqX=fbg>kV*&OLVGE@$@BJRhc>U4a@at#+KMiWoBAy-Wjz|s8jo3H)@}-6SYsciP|Szvk2BRwNKawwNEo9eA<kXFidT&83(tfP4$`$2MrPLWw=$^nXJAM<f?Ckh3Xr&zL2-lAR{-M#&xAeaZ~k;d~fn<&aWi8)PZglZc}|DG**3Mqn?uv8-`($uwfW>$XYXNw=kO1nYM<TNEk?%HK7mzi{k?qT#m%x#|5o|r2NQAE(b2PD5Gq+o(1S8@%#2{<%tA_IE2n#F1WY!TqwtG!b*?jU(K8q7OepAef_{qt(Rqv_Pq>rcD6Y0MCZ;tx0Gp^`qI-ibSE8-9LI~)DbpA`;x!IZdNIhZ6@RZHI}b2-;zsQxl-MG6vyr*6S;9C3TF<fY4Hw9r97#iS$R+@6<#y)TDpj?HF|pWW&#|ThU=mv_63Tc6!x0?`cQ>}p@Ac_vm*Q@_+%Szn3@bgUyldK7kj{lGR$M*xo1(PWYUNke1wybP9{3!NOOXN?FPY9)GRAH;^EVQiglxX-EuJVFaKN?0jeMg3X<fY3OUyX1A}cA62fEtIH5<7t8bBqDbY`t#lCUAC1Usa)W;63A-uSmjhs_17iSgOxK2pG%v91s?xR4H;f?;6|yPjZA2*QJfVP-aNn2Tb)+&{Q=I@S~W0X7RZ0$K^}+!fp=krIedm37N~ISj^ywN$n5*15lOCI!9uezYsCp~Q7dClxAWV~@t$hUqp_)IKo``#v*S86X@)7F`o+A8eUL$D2Yv8W>xl2j?a>HI+J+9N@cHqN5pyd8Y(P*l45#Nq8GdvgUe@{qtpkL88k}SlPQ4wSi&MVbd^767IA5MwNZ;c9w8v;e)+@t%@vEG`b+3Ro`F`AZ*feUwtEB0f;gHkuS(CMzL|}fI}6L3d{+j1Ri-io~(2s{uj&Dj$8~ArZ`ADT%`ssLSHPyN|y(y3L^5#;yXSlK3_FiWHzX*ph8B7BQNg@8VE@SA=cGE&dNB%>DPkLMX+z#e9m~%PsOwp<rJWfzSUR15b#J1mVQbI!9}41*;qeLbCJ^!nXJTAQ7eeo`Eq>2$;^@?ZwA9W<}5}CDSXl-3=<9;wuVW<MwjSF!d(N_+>LURJkY`z5RmP<g?dfWHxE(Jjw=T%rcgd~VC_TYDJMNBU#Ba-*~{&?>Y^Y=K<Uz|wio0rN4)qfb-OAWessgM9wSu7_BAg41uX*Ba!i7FI9Q2$fnh=k(=bdDHV(sB1;b2IifJ%xJL{IE#GF9H7)tA1(42{DGZBZe4u+j5Mz2w<MiGW#Eex}0%D~0)Mh3%jRwCZA*T66~iG7GBKC&&FhZr6&=yTB|zv2TKOzO0oKg&hGXtKoA+-O~ALLU7N)G7d?yLJgMK98|B32Sb0qL{HI(=uo}h2T{YY3pDZl1CS;A`!7L1YR;L(yRy-OdNC9FxIhlsvAd!N8@afa#P7&{fKx-A{Ldyt{^p@B11lhQ=?|nvs+o4^bMfQ@m*y9lZ3lCC0cZ2APIM|hIyw13EFyJqFc+6LQ8bv8cqpZ&nXeq)Z?(jrkoOCOHPTfBd0_Vj*?S?I8uz4tC@N|4)YeY-~0=6J0PhUwuVWEjgI6%GmcKyaC4#A<7aq=aQ86WBC~o9b3C-cedkUILJ7k#OcFM14U>e;h6r(za0eK!uUm-~JSJJzEn`tm6zN{iFibjZ8iq;2reT;QY<!81B;0z54x6I1T2)U*x``&<8VFcxk;|Z#=!n6i%@Q4NmgSy!hU9BflS#7Au_SnchsZlvCal-e2-%gO-T-C1%&?~AV)B~NpYIBWx#XB29qyS^A`5Giw3h+I3nDpAiMWywaY}4$4Xe0H(qVHjEQ2dz2@?z(3|J!_HtLih37d9Gkc3S;B}l?Mh#Mve8-`($uxS`32^)jqI9ik<v^TG0c3Y`H7V(R+^?ALhajsx7i%xrG2_bBueQeXiXK@yk9}W^wdG1@#aGJz}B>hVKX*CN=PX^mXOo}haHPpx{!D0_be74u@7I^fBK_c^p(so(QMAB8jrLagI7FB|655ujrA6a;)MDV=(7YK(<XVH;_&051G;a;-nF0V76F}%?9XD$p}3>V99UD*$(1k{)J;XMW;<;Gz)xW2^NpzJou%+2is7E+{y(=cZ)dxvvO2)8%0Qlv@K!;GznRu`eT+6(z$5Nxh3u!U11{Vr3iiP#7eF#1s*9@6j@sZ|GSn5T&BHcdCs(3>5Iiww8PqGO6RR50?aq`X1-25?jQD2rSW$cKrQ5QjX0S_Tz&=teYaF;@+DAW<!7Bxy*b<#vr5R*eZ#!NO*Pg@waKiOd6*7_X2yu3)Q4KN~{STzDA1;SSOwjug{cNFMl}C?fdg*qYAqT-=zCg?GZr-Yp%r)ol_Rm;q{^+73X}KGmD=NopTK{Rcrr!Q;h>?P=6Lvsw0qnRa07JU_FX-IuSUon!i#=RQf(`*r#sPhSf1u!<sx@hVYj4T^rouD~&`Ozo3h%&9X0SnfH3F>0TJ#t=%FwuVW<;l?s|s;)*D1%yK+a!BW2syo1{y2}b{SnGp42gLbB=$zS{i&Tcn-egxhn(|)iD&+KvCqRWCmz4+V3K(8fi;lH1c`=VdO(@y2t1+LG4sROCxyZ#(<B-iG6$s*omPSSJa6ZeF7-rhRT$3=Ybhc;62QB2NRF?WD-n@#pZmB==fLEy~uTVD8y5dl)cR5xhx=V?Avx!qisEmc)l6MlbrdYeRQ-XBZ<b(>y^V7o6?vfd2hqYW)YWW37zFS+vq{HTY!zAIxzTx(MNNMESBw@3@VMg|FgHnk}rS@u+mg&n-t=~?Tn=kw&s{DD9+RT@tzQ|&8sdHHlk@sla>oqw#MJK3K(1Py47I@0iHaS&Ew=52LW=>t+H6}6?vpeoPEXltXrQ}6*NO$8v>eoHJZ5Ld)+sT2;lWcJ)4ptrYfNyVy5K0(?VUlnQP6<|zGqt=A(n*fCPn;5lBPB?O4Z|==xT#a3y`=2YDj043Iwc%65u_PMGeg^{LupoaHf!E9ObGC#HLPEk?IY%mb-XeUt1~!z7_9jEGy%T$9e`-)oum%4VOYbQQB4`MzF{N@?<8)RBy83iCJ7sMN|1!jF40X^!WRs|FtkBtq!{>(n%fTy6H1tdVUqAV->|bWl}?cEh$*lr6Cb2}!wYo8%2C2M%v}UK^i?XKBkHPi0J$6`Dz}SuI=ODfeTbK5Y}b$1vq65-6CMpNsC~G)STy%`xEIxC7bWUBN?Y3#r-<nz0{588qDEW%k|+L0@Wg)@M2kQxwF;(MB-XE-=oh(KNer1MC!cDPpHlmv@(qJ@Df<%X#GbAEUtD;!;<GTynDx^oOosZ3yf0zE;c_Rp0_Vp`k5Y1?SsOIa6={%++n&4fW-B2qmpOC3aJ{*BI*zzuSlTP!b0lLG;({-OrMHq#Mc#n7wAo6WD-K*Hggdt#=71|6!9obZUy4ik%<)`~t_R|L*Wo@c9YL`qeg?n|9dIxZz9m<Df%!pzVc-JuqTQuvJ_{D&R33;0!9f13Y*FY3q9v}gn7QKSe3jZBh^yOt0gI(ra8$XgLP-!kSKNzOO_aH<jEf61W^>o~;<Mb)w;2;RAet?nn@AdVU?z4MN-ABcRN@*wqD&l>i|%rb&zB3k!jm90jL(DZIzU2~-Ggr}NqCmZ#aNNQ;^1MJaM-XlOcLJCDS>sS9d?m0^u!D>DyIa7?R>*nmK6@C%xOPZ$p!|)EiQC%E&bJ+^Dl%4P3?nIp!NY%)INOk3ZDKBCh=XE1$V8t*5VWSP>DOZqLj^r<A8djYrZzisC^jUc+<5NGLq^W5D~dX51nnYV>M1yIj7iIeS^i}IZdjDMOTtiSzCQWK5!^j-#{gZo~my!WWDDGkhQiJhI_aYNqB=X!21i?rOgN}3B~->X1n#Y6y0siWya<Wtdr*e_TrS_y^#bRA`H9IsF2y*UX(};ab_G~60eMc3MJ5}P_%=YCi@&mN}jVooLD;|25ItnpeLJS_4z?%c(wMkT3&ll{6<P3iCJKFSd7+lcpVui=G3w=`EQRfOge1Xh9!=anzS=Hv#}Gl5}r+MQR9@TBa85~E&x2oDUly$yz1<U>Uh#Z*Ve~kUiC#*4Jf>1;FPMoWt<Z0)^%aCTCzqkj2&Ru(LPw|_OQ+CVc2gA!?*<uFQ){<gc7D<m?T^Y!z+mTmMtlJ=25TW5i?E%!*fCHGh1Os?UVI*@j=S;BR^PX$;>mg1u-<|R<mciRX3mevBjrT+bx~kfghB)v9dhr9JNmdu~C!fv!KKQlp+b6&l0T6sC^d2H6K_m;-Q3Lk=iGQ5>~NVA5?JwZR_439X1TZB;mfPeZu<8dZPBJNM`o8OJ)|aMhq#LxxC_*Oa<m_9#*D$vTzaFbDghMcS^W^JZ`ZS_f|_kW}mZXl2c+nTW)H=LPX)MR=te{*?<$cb$wDJx=R=_vMTm6_|PrV;W2H_)W`?UOu;bWuwiSMBy2Ja2WTbK@bUt2q^u2C>p_)0Vn5hq4a2t9uyTZwNb3WupkoJM8MzrrxWXE40K{&QN<95QPTLZbopToQ)@#kR*Y0*ZykzLEos^{3aB8&jT2*6vsJ@ZE5>LXusQN~Jbq1R$MpYshTdK6Jc(4>HS)t#yg|*l2wq;jhjBSpZNlwbfpr{sIj}wQ?DPh-}0kw{UxpGQGQ)ZF11uR`_jwYP;Y(-9qh7m!0Bb=y!Vp?l98z~WmGLulvIVD)w_o7KMxDR0g5C-9tpjmSXJl`X;fMk--#VE<=N}TI+Mdb%wRtFdAa)vI{a->|YXTZ2p^T~zcDHqG<U#Qx>Slzk{rC%;x@Z!bNB`%hmSxS?-Qo82FT`keI*I@_=hRqjyCf_h|qzuS6OcJgDPww-6(l;UxGk0Crch}C6C0&a0H@SQv))Ylbsk1g}5oB7PsEZ&tPK3n`l14>uva8rv1l>tREP|M3swtW)0~HYEl+#JG=vZ_{P+2=cG*eFRn4I-FOyi{Wp;;n8)EbC+RW|Wi#^&fcFTE5nC_fu=&spzj5)B5)8^YBM$mmkHAI-;<??tt`X|#Bf^(k+VtIT8W;8sQfCfS<Mr1Cpg4@8NNtxw-zu_I~iMWc*M#q`P<j|<WJ4V`yfrCvi}vd$waq1b(sl!C;@>oyTrXY$=pK5(|RQNWXBAJ&i8C2{$%HD1}`LJE&+WH7$YwI=(xVk}i@)QVIo|D-vrNpHv}(Lw|ZJk^@|k^-?*+@$sfBz|Y7o#|@88m5uXv^7i;Hf;@)giTw+Bw^#p%q~f|B7q7jH5ywaGdIns<JFqa2A0gshYZ6lP=bfkufDPQ9^>g{G)bzxQp~g>Cnm5iLL2n1!7<`~=_y!(g&E%qLUZzD&U8K=Whe8Vw9!a1bBpStkdFi*Yq&uc9q+qZ1RrC>tX7DoKc_^Jnkz-^Z+1#VJ^-cpocCljc6Ul750b@FLDrKt8pxvKt<srrsQGu9?}Swl&Fw3TE|FJrlz?(FHo<U6d}|%!hI_p(Nw{~0HR4+{9yi>HZw(G0Zg_LIu6+o0Pz$^>B!)G!Fiazz85Jt5D$=II@Txsjg8m&RhrFJR1jBt3U4~uw)}{}`Jc)W?VJ*WNuhY5O4~jVuy!KI4Gpu3F`5PJ5N>}FLxEa<oV6X%IXKbEBi9=>sV|uFWHc**|VW(lu@#({`?@71hDju}#DC?WW+20tsacrFvMd$yrXWC<#<(58YISJ>?=6R0PHC1)Hz-Uu-U{~dQLbVY-Fa0tUNg-42eaJ56lphvWP@O<iJrVWgAZmunHuR!?$fN$45?yM^a4^#j=32NWtRRO3xuB|?P;+E7-n@zobD3kk<W+>39IIehQ-xKLlPx_lD8q1eF~1Imc{vxT9Skd)xwbHz(`S7WCyw;PSv9jxGZ^;$Ens+tlOeh!zO~)^hDpNtt^ob|hEXI(GZL^trv&M+c^D=M7c7!qg&im+B|-^vFszE``Xpd|i4OW+q9X|#hhf5D<B<|1;oQWK^&TlfoPma|VbWpaFiaB8`{%G{YnV{NBn<Pkek{STP6E~2W}{YP<iH~(cr)s~b(NWu0C}z@g5!ER&yCmKHkEH}W#-aJS=d2Om6^>uC6E(mpjjA>k~FBsqB$4_b;%V;*cc4EQ6kSK96kUT-imM7k^VSH(?v0Bo2xRcU}JRaA@L34BG`&=*bxjiZc-Oi1XM7X&-1JK#5ZgN-jSRVhOc|*5;mVjhhz;KzAlnAZ1}oJFl_j`2QFc3tLNA>ePbI5^YX#v+D1W{I(v6&d8L<ZH{Kr5Va+pXkiOB!sKPs8TJJ_CGXxdHx3)tVK5z+R_b>3~d}{`tI~&R4gI!z~$r?6%U98Vp?An1Yh6KZHbr`~_5?w-HwC{0btjy+-X`or2Pl2w2Yb9`#;%Y1+QG#tH-I?}1A>o6>W9?=s#u%r3^B!QB^B!TCrEb?l#$l5%%re$?)Kr&m%S4EyVj$f?79EC-DzQTRhZ77phT(X&$N`J9WVJA-){Z<KhSh4{R?A5}!!V>U%)32%>~Z<A3f^O=XokZaCdom}#=VMiz%WdlfxA_%1Lh3e(KPCS<A-+z!+6lO=yuUlu=_)0+W;MOM#R2IR(Ax$higmh3Wg6?!aIUt-$$~B4fm9TmGG`$cwZ7``}Xed=x4pXWi0Yt<Kh0C5_q5{z|LU!U~zai_bmu27uCPS?6uXw_6Wm01vTynhMkM!%WE#O=3MRthG&LaJJa%-f$J`R3;^vOOY0S%<FYFrLQg~F?qK*(aTv=L(#^o|p?ct9hc+paQ^Igh!J$3(sV&j9nA6!4()isi(ZOM^BJFUAu8lp6(|H=Z@(m+*N9KXotYNUXz|$SUu;aMQcSgl5s>L2KFUC`+8w|U<s9`QD3A1<>DkgMHPz}U2Er2rwUaFO%F+y<9-avDZUM;J-Eqxt9j)DvtFkIw;EsYz-xCREaPA=IU3<C?t#-yZmI2X5qVYUOHK$b}uWJDt*p_Rxh9BaUJ-Ymdi{o~87#<a|&C_vO@8bb$XZ3sXhBTsP+C2I9<upFYbhC4M_kgVa*)DqpnGK=mwZWu@6IlvJ{N*pXo>}-i{BTBH;!3jHGq62e1dq*(rB!qQ1T&&btzIlIro9)zgUn}7_WeFyhAhRPFP9_%z7@>_jHdv6XVIzutz?^{_sC`)2jjC#FoPm750c)`Js0a<}#Y5+t!##&pZomGUc;1-Txu>LJb%Q!58FRECwl3K>(9}5|u}w3hBNpr<QsOXixcWi9%$UJ)<=`Y7Dc6POD6O*=UFl-53{t`u%+17b=RE}v&>DtaCNsPHm$1vi4&mU?O{ez2DS?zl*T<GeYv>7=U>$BAyi)>V0UZXv1SVyrV6qQ&K-TcCCz@?z;9)DE>rAl;Jy~shuaRKn8zvT-KCI!LBk>ITRRY$ukFw6?XotT<*P6?ptYKoI>6R%koU&egIPddU?3H#f*HOZ@vEr9JKX(wYrlv*-fb5x8+pp`QR}jkv_+TR?!g`K!3Roi+nsEfIG2I$=k*s0E4;3kHct|WXNH9Dc7McM@74iK%)B{3^J>04z6GKhk4m)rdJ|G?56AT}ag!%40iE{pI&*DimxIyTx_s83gv%ZP0NF=NcgVX4sX0xDG2pCHf937VRc5nDqeGiL;1_m01I4NtG?bu!eU$Qi~;hJRT!jc{$Z<x$n-j>>VD;`cYnYpw?muAYysyrNqZUSss8Oz;q(;e}f9uE?>iEwRcC3$=P`ejp{Q=%-VY-|J9Znu(H;*=N*&9U1u7YR8hYq;eS9XlZZ@IGJ|RHRXo5g_<Hp#R%}gZ2$W$l6qk;4KEiba9HAr7<45HS8YHD$-tH7@&=WVchE>e18x1Ky(=Q_fT=fKsN%X#KGt=+v7t$3<+nfZhkZdRq&ZK({tg##j5Mp#to}gB*<bvqhS2BTJN@_N-Ix*FI-2(B`D}earX$rhoQru(m5~hG^Gdior{~3N;fs_a?@0(%iWSguZ$Lk4?~A}*DpXn@glJ8bAoVG)-Vfppwmvgpu&A$t{o))2^Nn{?luc9g@q8_;&HJ;oQ2cR<J*fh%#)!S$r?79z5y)nfyYSY81Dsu+Ud{ei7pFLU<VKdk3+DA55kt%b22j$3>$u^*m9n8p=#!EanLjfdx@0D93g!ZUvd`t^>NSLon-+Ma%aaefg%JUt|9=;mAq=`Zm^!2Y_MRcMdn6!YtF+IMM?;d6|3;n$iO}!brB83AayJy3~PMda4RDvxHN1~MoK`t$Vu4}1_OZM1Hj?!VEAQSTq@Ag?1VwHEDm{z?m%={%j<W0o)<$M*DlLkN6u6w?1phL_de4%@E|x+*a0qcPacN1Vp5_=31U(jS{#S8;(<+ARQrcvBp4<prBTDMJ@x8o`-kDF>+k@qVI&wfTeErU)>`TIyxnRw^B9)hA)Y_XTG;L=VR+&w!G^_BI8jcCoQoi>$J6J1>&y;$qD%3M71mlVpvvYOLU^%Mw^6%(;C3WbV#OF}9H~=c6t%r@)YkCCQDW~f?90Hlq0hwFn5|*4z|Mjpia5vME4QEq=?5M%#-_f;F$fr*w1n9h>N%2AV(UIMWeE>riOxrYVUxaLKIxUvMhT^85YVyLp47E&Bi}{Y@BQdGOg<t7_k1NbbqT{jOc^9=*l-`3u7r72MD>*}1(+{3{mIMvWuafNy4ay?beK!6xiC3vc<Qm2VBkuv%$;^jN-r5(O<Ua>c34H+LPWIN%o_H&OxfYtb$PX{A<pG-JWv5^(ceI%HnXsh7r)J@!rSmE2#x>|IhSJ=l!0EXYd~ER<jB}SoDx$;iJ`#oWF-uPaqQtCTf-OX46+Mh2OH<gV3+|8$TvJ?2_x@o*4No7!R6ncBDAsFToufr=1>CGxXyq-e9EaYIVC2aPdA*R08`DU!$HO6k~M5PpN@RPlutKi7@p`zHy{|Eri6zC!_$=TfM7Tncur{CI(xh@?C`+tjl~}Jn*hm%3B!{_i9x}z2?_Ik<Kd8CI5dI7nKNll)^HCx%tvAkU*1Pso8;474mYq8VynUt`-5Sg>s>qAMAhz%DB(Gp4}+B{fpQtA5i|rn_x85_zX8Fpe}Qf7`Pr(jPLJD_p~CPKtu?GuY(B(%I<~3v;o$mc4Gb^#1H&6}*vlTg<8Dg)k6;-0VsvGu{m_=^kbJ{?&8LGAu0#(<XOzQg14`JLWZAAgovbuP9Gg?ZQDVcM)<`%T2mrDnu}sTC;<zC;3AF;7I9yTT5Mdb93J1~>oiP>hUDsxg-%tD<gS`SEPa{7D1jE7v_Zj1BCG2<}FYoF>{fXDY<6M#UbC;*&e4_rzb}UHElPXhdm<`DqW^9VQmqW6K`9=u?*Ghp_&FFaACo!tW1A1^h?&EfGa0}i@OLT^N6H=r^XljWrY%r%I7#?Rn9h&Re>e8PysNVE$f?;z`iKv|L{;`rzj@l>eDW7hz)IK<<-ZZU|4*Tg_7y9g|m?WHD2&V+YY~Pq1PsU(kIy}fMIwWh@uu(H92@h<EZhCV%7-Vlkf?>nG38x0bgTUe}f)WhpHLJC31hXR+4%at4F&&1GhTnsM;fb;z@ST7#)IL<$%znUHC_G>L%Uz2g_1hgeu^$`+3?soXu^)^#?QCM~2LpxS=}366)-Vzb8-DIcFih+RT`MyWp;ewgnYu^?80LH^p;eQSFxx#6LreAp*b3;dD<VQqL)BnmcrrLV+^Wbp85o9gs@2{fstcOu$K60X&6@U6)~%V)uQfafe}Gs_!l`h#@<H-mFp;M*74PLxof4D5;UO>4Avq<ens8TZ7>4oOry=2?IwiuX)N3Aeqy!QSQ#Ii+J0+$f;bEq4OsJYLs3doNTV{7>NWXnSkG<iPrQ<lOWTaa<{xZ-OM~mK8hUxX7)HfY{BF;MzfCw)F>#n#Z-*C%j81fCXX!4HHLFOnysPI&c%r`s;RwowGK};g%2WzS6_d5KtNMCV^zTrWPt=PsnF*4sUu^$|gH9QFk`_lY@L~Wu1ohjciMy3&~>*B1w?_+&W;nkn8x@y9F1K%*LD+$UfdIr~M^Xf~2@)rJc*wQJXUGO5*an?hh&W>FE4i2uY2DTvXA2<w803{qIBYZHPz<^qQ<f8MSuhfLgioQ^1%R!-2X`zyNwlvV?l`H}xPdNY}nn}bdeGpm0JkEDxQT!THXvWm{CCMU_ugqgMLvbZ>1mX^O@hNHcUP_~xajv6gvOpnxfT=eic^lR)W3IuGs*l(p(l_MYOBNayj^7%_a8E(OwX?^>A)wfAG2xpK?jRQFUtXgUPRS~}C{t^mhH_$_i?W7vG(8KtMB}r1r$jger$pQ?6+fJ_6v!#jmo?0ja&n^|>9D?6?R6H!A{ZXOEdd-sb;)RW6ykNo4i|8T5k6r-<WR`F)NOZ7{XvcWtk6@Kj<JzLlE+?X7REfRkie|`*bUVmWpqdfEtg^!N785z21JN1V&Kawi6bwMr@UbKWbMNQ0#Y*I*lftJ0jM{4@;0w>8?T8<Tl*32fB0qc?j!RL$Dhp1c8#%YQ>GDvNN<>m4NOK~7Q2g~s8K8%1<TJ0^rRb>X%(dERgH`3S#fX|>xjP6DS?pmesND+u9t{AjGYp^<donwf%BL%dQ=yKLQes`--5bS;yM7$l46lbj<HqDqyEbw?yKVavho9$uRP$MBd;Wm?EC{`#i;=%4N9jKIj02E&?B2MvE*&G&VLST{hkB0hLvJTYZymw4G$8AlR*eaZ%dS&5*)eP$tl5g>$QbbBA!<`Ii~~{4G|zL3>)rqWh(e0AYOVR<eI1t;P&g3h;T^H@$Jzmk+(efg0sNz*vd<zQ1KMsXEWcimu$B10{JM!V-FpNi4}Vc7zTQylQ}3<K~9E4EQB0a6brL}46L1rC8;`XC%Q1Ea#%<KYsB+2x+S`Lo}W=VC2-&mbyKDcH0`6%v6(owxM4gfo}V$m@VH01Ji}TxQSVpu(3W8>Y{T<2c!ss1!?5S$q+ob>J#yS@9HW5YQA?PQLJ7t!VH|}L;FPlHf*~|($tT0}GY%LYvks2~hQ}=7alr71B@82IqZk+*oDK{R&jlbW1drHz$%n7lY}{)cBZ1-ZN*KnX1f!KO6A<SsEpeEli*x;@$9?27&Dv+oEqYy;oA-;SpD~|{CHFM=&&`D?p|-v&q7d0aF5G*{&P7lGmSXJ~lVB$V-}e`*g){T`j5+?oS*!v_1_3S|4_yZx#|@TZzyPqtioV0y0>BZM&_)$stcr**AQ{b+ydy&tSQ@UVTB4E|M9UrVnTQO~!&yW#Ra-DrF_P*=<FLv2BTY$pO}!z;#$pYx)nOzUo=RQVNyG4HCCu9DIcs($ww2!l8u0vJ(cXl;s3q@`MHhC@q6<4`(S^AzI=$^oT}w46&7up9WYL9&vgnZS8df(3tQ8|An2K)|aj7z34OzZA2L-J4G!~B(huM2%!m}*qeKBI0x)PI3T~Vpfm(_vJJ(Ww3uKgf)bRmD@m9Y8}7ivz?5#~bG7cbWSY@vx4i&wvRv2=-x<u;Tu!mpIBd2#f<;SuXFj>j{F<7HUOHGSztF?h($F|4^xv^dXvR?o0D6T=#c1Q;$E)|Qf4bP;-Tax7-dzN>SXiCMG=lLzKIu9}?dQ(q@b-;mU1s0F&S4e1*^P2WJKhT1lY%VLhLQ7qBLhQdhw!y|&>k)p(iV0fGo9##4Vj@36DjS3MlpYRUL0U+`XGc`FZ_=ce-Vw2^Z!3+w%;Y=HoSuAIu`E<CJ2pi2$lL<8>x!f{m5t9E^B3k4d7D=EWXZZoEs8F5_Pb_H=q{zd0ZY7)LsH?)%H(V_6SYF2DYhz;biKAlp2D77Iqhw|w43Ws?NeMC@O;|<66OlhB^X|EqYxJ;_naALiP?nPX8YXGv<8n$AR3432ZfTIrTs%KY6;}>4x%32MN@jMGXUUVK`bc3Q6#zCP2F!UI^N5x|5h^=Vs+CMT1u_AsEC|HpO^g)_64614SPSc@eV|<2ke3?`l|+Lz)&Xxt?K3p<B6`k>UBMlb6+b3x7?J@8YY;Da1Z*tUFdvj2W3nzj$~+E6^G|Y0j68FETumOKZw<z!*dwg5I5rsGAmPgd!-tnSj&+L7huE7~&W~5ocpO|Gg>Yns4-yPh=J>c_czhBbSA*^GWqZ|F!;3v6HOp$RHf}m6wTB(I>UL(ucjm!fdV3au%7{#hV0h%2<2X9Q2Psm*EL4weq+{b^jdQaqmhMRA&o#-+e3&C3uyhrCG#<f`!LUl-7&#0hWsV>G5*?B?Y`DiES;PCw94Cggumi(d!ErG%zBRUcB!(@{ugn}DOD(!FcvPT1KzOi#I!eO_57H@dC9Ft&-Mn3_$lBf5<8aI{49v8X5E@O5wMtli=6;Aq;lfDA%arQb*Y^&?RYj0Ga!T-yoD!^xQ-bF>B@((LU=gQ;-#e!S-yNrf`PzT2(>Ia`2_97e<f;hLsM0rvUVURj<~VCQV`bfb77j6P7|AJN*ziGeN;G?@Z3}I)wJA+(u$&T={s0WkaY}%*$tfW?C05yizYH{|MA2Fk38GF3F*8mH%>rz7LzoT6$hs@;SkpI<VA$|f1qp@?ug2hrm*|F^B9SB{v++oH44e{bCdMI*>!3%R5;zu435O-|ftWf@WU4r_WO7?{O4N0L{0eZspaX2KMVHR{c~~fj$Mgd6@x&OSyyhgIohPM|Dx4B!L}cZd8!R_E6F1*HNy7=jFpCrNam<kt!!<8>(nH6Si!?H8c!Zsgk5#~<$!o?z^(L4~UNakO-0%qVnnw)7NH9!!&1;jHFYdY}m)o6FJ!`%&xD0(5tzwTQuX)VYFcJ(?Uh}9ckd376)iCS~RrH>(g%DT74+FvQ;pH`t8HUFp;W5MTC>jr=1&OibHIEmD-CZx&VnWSwC@{>1y&%5HDS^Wjy%rE9x%bPyH6)_TgUf3k`4SzHHB5QUqqc^}(ERaQ!(*w4J@!ZmBp5cG*E~{dcm$fwM5v_*njAxhJB%oct}?Hgvgi)GBKFu}c=!??xivie8yLGaJbVd{KW-Qah7UZic?=~%3!D;BNzgbIip%1agXWarm=()Q*~)ozOOXKhhODDXK!-d4@!GMKhgIbyaUG`wW&vwbHpt>7=Rze&UTY0wX<o&uGa;cV87OPbH#`FLP!*aX$@UuV;Lhuszy}Y*Nr}aQ<M4Q4ST2Kt<UCpoo!Y1Fo`!D&rAR#FITov8vohVip{&iD0;l5qB;+v}7mI|e#2mnySZ&nIW}ak6XPLY8<SdYPD{<(EzN58<M>FlmI&(tQwy{^^n0d_P7KvHxL>x7Cyl1B$$-UVYcVq`q1)x<Et(-;0f#!+>Z}i((G8V_XaTkCM7Puw>!$^a~0cR{u0)_`IVKxEL^DIP^4X=;#HKHGjkbQsYEedWlAQ(QBjKyid@Q@`u32S)J5}t@t0!L^K^U>(Ha1i^YHD^XJd?*=<6M^9YOPEhU^jP33C8vZ5phL2T4FVm50sGe21S+LFocVDK`~W$%Ct(dswr3=3*q}AceYcpAG#qQVCSWb>Az&@+6tEU<3|K4fY8i{rZ@^mEN5C5NWp1!;V=MNWvB)}JnVUmRK7ow(VP`B(#Tp*$ok$pVA{cfRi7#JzuC#t+_<;lB<01^}V>Z`51BbD!QlLCd3sd5H5dxosAm!m~p`vHGjE;(O4k1j+D#{{AGwzFMzc4C-G!qSCl3~qPA&fo`JyF0SL>DpeeQ`bX0}nI+as<JLD6}X`GbHZ-i^@@C#S?v&6uNXp+9T$JoqZk^rBFqXqWT#SM_2h=hq|gnzBtqtU@}gL;p#BoJrc9f2n<(C7&;>&>uIQ(4h#?UR;J<`9<GFC5u~Uaa4nV=k%LwN2kW|Q?FVrYq;PHd!@?(75v2Snkk8pjj#Uw)c(_$T2cp((RS~2zUV}bR*IL6#t>Oxlf;J}al;VbQkSh)og5hD_%Xm2@HdJCIP6-p!ejI4)oSc+x2UVCe15?T^re+S0rg(nMvV<)rbRsw(Jz34qcD%)0di+HBTJ({7z&&5DGVhD)$y@PVIi&<OG($SGgsjTD8xN&w5YCF#R;TH(G?_-0KTLCbTf~97lY`+w-prJ&;bBU6QZPJ73G>02#959Dw5&6i<O*ZMTqGuag9v8b=z5iIKddUhU~Y-d39HIF6dK|Cv+Q8$t#rO>=2rx)slf|NOLV%>-Bvf04W-DpcpB4y;nb;&1j7d7hH;qLUR>`DyLzasRjDXtmrLuJ@hGYXLY7~XW>NS%R%Cl+Ha+AVOGy>#HP&#RUISU!8HT5{;fSnZq*}KG!=uO?=hKq#0Bs4Jmgr|lPKiUy9G@Bt4^P6pK{cEaZQjBk+K4qdYZwWJ4=i(>ZFVG%X|o+02R33&%o=vs;Oyav!LUC#3B#I#kYj}5l(B9wBi7`s;lcIFsW~N@NSF<yDk1mBsNPGyvVE}KwJuD)V9Z4yT0=Z*K6Jr!t>K}e!~|h@U=ps4lwb~w(<uQqy1`=YV{lyHfz$R$H~=k%uBk53iR>#TBL84G-5qMN*ySU%GQe|vPmE*US`oV*cWh|8x-PQPdGn!*<#sAr&l!$Ty%jIE+SUec1?YRMZN&y55Nxi?lcIeecCFh<MoQq&%*P4A@JytqaeD)Q{_bITV%G4mba*&%!#zeyY#5?<9ydHKr-UGD5Kf8pq9UinHWV2$Jd^vw@j<d_VKGzXW4!fi9Kd)@#iSl5bd$A)lPtR7tZz&Vh8G_9J=e8;f?;z3YaB&BC=v`Cf?+Omk@$LyB^cfchGjmMYa~;qZx|lu=E`{lY>287&f~BHF&Fk&5_H7Yu*k_5|NA};3Wg`=lpwz0-DQqn$v(Rfl5e=r+d+yOHU-1cp5ybLp_r+}bb{f*>F{J>crX%Pmqj;11PRhTyR;+>1jGH_4pP9H;oHFx6hRsvMtflaC1CG{>C^(&@++NW4I3!@H#7-P4TiNj^FRXbrnf|wEp!Y+!c%ifWD<^Y^Ro<n*iRzv<g8%`Gs-C>7&d%6NHA>pb_OBgNi(b=S;K~J2Zw@Nd`)o<hW=tiFdVIcx{kAuf83_Afs!e~Wz1pjQtU4Mr6YLI#Ty)b;l*Fts_K<E7S~4Jz|02uP40>S(8xZA2{NpK*cg_GE^GKIQ7hpg3xI)6bg4WY0pm%ZU`+ADvb5q#T%i^crOi^R`G9Mc_A;s<!LZ@mL9&Jo-%itcGjFAP(8k!EYTU4LN?_|;#7+I914kZCOOaD<eOuhrN>sJX9GG(C6U^`RH38Ke8<d^EJdxuTCS@swi_VilZi()yT(6i^It_dSO=<Ob4Y%M?9Xkv&M_LOkbUe<TK$H><grvlKB9zz@h7<S>E>}{_zO)zukr-$5g)hS@r2PO)R;&T=`O@~{v(Nz-oM0i%R;H?h;!Ny<WbsEwo*{lo{PU&T6r_<M-W74}f{vew3)-ux!7x({<`GZ`o%Q=4MO(U)CYMFW75+*B2&GTKx-2?{8>;-StA<2T*;Z(tEFQ=z*tezMnX`uSip*|4Os@Z}t>LWx?*P1)FfDrmQj0BGZw??xZ!b!3aVn|fSXQba8uO6x>^xDRn(GFEQcIrL2)q<f3%aj*V%G2g9fy440^WZu1Dv>o_g>2YCNALp`?V$y!+Wn~FnJi>I}A=9hWCAklZRo?MuOpK*D{zs4DVaQQ-@(Y+%rl{9)|Z`%V6>_y!ToLlZRop?+ES5!?3|>5!;po<zuDx(d*_`)-ph~y2%-FO7zu7k!auhyB(j&RksXz0U;398lZNQMEgFeS_YH1hWWlFJTcmL32l<oIqS#4d?jd}#cJqkXteJPCP8!wf^kjEI6%KsrjA;Bje!`}>Vn~AT)S?WbtJmnf?*A&L;KDoL@<_#)AQ$SB{0ErsQQK(7@n2uaZvRQ1E$g*mE|C;;eFob<Y9Oo%teH@Jqv)UZy4>PNYytCX6Qpf!h5K`v6la0TpG(&@H^xpq-D^*zS=Br4ckws`mRMck<C%;5|E1wlw_E!b;pHnk7HuA@0BFlaoWJpXy2#elu+pz`G}N(I3>neeZy5nkN`9$yM;e@Ly?}3L#w`l<4)hu2Q?^Q0`79;nLG>&3J94Jqf2-XFg$5%*inhDIu4UH+^aPlS!FETt2I33NQsP61}RcvnzalL#5cT02_J}Wcz?GF;ndSNicI?yHyoNG(e{yGc#^dY4hV+#bFT*k!+XNvgW{Axf?>mbl&WupCbH=Ej1rTFVJF;kJ&psihW8}l>1WY}d#-pgc^KA0-uIGEH+dM&JivTEx%rcaVG$7+Z!$D+MKElT+K2Cl!Q*hKeW(bMsXofnJ+==CPv06&DM3XY4c9?};mOr9I3(ZjUhelWl9~4@;e+EFMuK6(eH00X4fj#pvF;rl4DVc}*jmvu8JLLnXf+l}k&TR@R@oquzlh3=!!YHp{0;*L=5bnrip~@zOcvD?yF9BQQ)~!_P3arr!okS2yi^3q3H7RSk!K=J-(V_46CJ+9eA;uF;VM@IiRA>x3Z12CwKi4c!^M#ybs9G;6+}j5``Nu?;-pC9hLygGDl_h)q}BNxFf6Mj6uS*p_oIV=VXocy&MTg<sTV;)g{C|%MJcNyp_^pPL^UkM8k5gcIF0&%E7&R0yc%&)QQ^eNiXgesxe#SLqE^#{r5z@Ds%$e1kIG_R1H);m3a*9WBxOj;>DO>PgW=>0SYflUL$ii+)#4g^;I%br^vN1tD<??oG}cDKZgQdkn?%~sRA~IroDvzKC<~K1Q(B>4wwAJng{ciePKito2(d}UlZ7LdHV#6M{hUN05qg9KL8QK-60>F-NBE10xV&824OHngOZ9z|HOy-&=8eW0jt4ae<56uP$f+u<;UuXXlr15~J|{j){^bHEyg;*t<M|(?X}n2BdIU*4sxF$hnh$A1vWCM6RZrswDB;~!Ps0P0@J?ed4-$rV8X0(yFuc=_dyp`^Qwbj;4DYmh+JRcbNH9E|>S>1v!@I4Xc8D;%)9Psl3B!wBO86jQSkS&B!SH0NryZnIVwd-Qu)bj=qDzBXHCqOY6`KXYUipSYs-8wLJc{aRaEMqun~CZh?tFziqkTU#YnbnnUt;Qf!`0UC!tsLTtmUL*8@}NK!{UL|qMI}f7mKG643D^a+QC}GJCpDs!ti`4_1IqR4u%gjU=7JPY|t8(Nf^74@Ik^bbSi>GFx(u5XUuc`MOzO%!El@KZJC|5n^mO4w1(p(I3%ZpA+6#ffdgAdr1V_`DV%nsgecoH_mGz846isK!LVVi!hKr9EMeG#k+PsbE$us7r_2?^1$?twVh0mX6jgvA&4Ua_mp5R~R&{*CUWo@DQXzs<mMiAO8icyu<tn;ED;O4ek&epB<D;4lyRje~pR1ZYS@@qLcKsknRGwDtVW7vw^StgsmfOjTHANw()Ic!2hw5nu>>J*Zgby-(Bivy<jzdpoMzV%SUp?(G(>HdB5{C%G^Q;HYkzhD9S+-{fQB{YTzOl=yJqHQHt6f&@ImozSw!^AD^)MXBaaPX49X_VK0d1vIIUweNo_SO#+mlx9VQxZ~$b6T1L9VI<h!s=JC|gnCcmm*&6C^$o9B!H0!fC)a%oIn9KO!|R7qP9VMVGD3rB!?K&LPRlsCkgs(ss(B7WrP`mZj%UlVL5@2FWA3iBlr0+LNW|V^nE|V0aUmLBbfEF#xiN4NWiGlUD746fGf4T$fpKA1o4YYiW2;Lpt2pH#{~NZsr?K`gB^grwI&ezF}V)d_1!IxQ0KX->}9od^q(YkgQ?Db1d9}HOvk$i!QYZT5tx&%FiQw=P40szGLv*lBydL(IxJw`UaPF@aU><qyyGM3}H33=+Z2@Xi3>Y8=F+$;3<J4B<!p_d5I}^<DwCq6{~L?T)-MeO!zD^27+b+pn$buR!;+hVZ#zWRH93!RqbIu#SL%cX^%V)vLuOcwMz@jDZ#MIE5TY7OOZ9GxFh@+>CCW6jxH!Vc-%RC^w6k%_zpM&VI5Y1dJKF-PXS89S?Xz5GXs{7H%kuFnldr{zAWvtKpu1C%ThCpEis?}QN&uzApsPs%^U=6XjB9#c??_+d_}6h(fi=ebCu_imgo#v!%P!1617jSoAe(muZ=Jgcw-3zaZ0qbhDBW%<y8>Yu*qDcLxkboV&#TQ2U8U1JZMr=W*+n+Rv`5?TvLXTbPd;(;Z5W4!zl)=g==ccv?ivh5i64Znyo2AFl@S}3~L;RKPA55ikdRB24{5=D_O&)XUzn|hW*1Zq}q<*-fGcR)s)#LDjvuh4tG{lhKGmev#1!o{j!7^C#OV@P6^))a4$}YgMs0Snlc2#BdIAv*0AZCG8>34gDC=WnQs^n0%5Izz8D|DupM-oIEd@TUm&N1>6$VG!=`J>YzSEMrsy5ES1Mplck2Z66$sNIfK|aati8coiFFkgS*{M-DPgXr3>;+j4VjFbn@`B31j#STnVColwywnP6n(=o3?(<8@ccPjq3?N4(KkHnG-5Hyy}}5FD{9Kj2!_X2Q--Wz(=}xXhU3|rB=E3j0hobd+6>l|ImlXcu9k$H(s#fnK~VLLtpnD;MBLgzR%T|rm{H(F3CU|EyiH~1LrrGRHdn<;@U^pMN@ngM8s307HaI1OR~iq&DPiNnpSzMK0SilXbL=u=fsDKW@(t&C1HnwT7r}6x+NmgF)=HQvGjC-LJIX(doeGtZHQdBxRate+fU*$`>!rOM)_<K)a!S+{L87?fk<^qS7&cu~W-Z?^D$nqIl#;?y)abk-F=H0dK3CP0(ay39(Sd3XwrbE0K!V}0Sj?bz{_4r`4G*oR48d>>nfY#Dn2#8S6Zi|tg=5yjaEim5V7OF`hG4iUxFEr>;cy1rDZ?7>q}G)|hBdFEyj0fb=TT+WT(m-Rzu8$Z3pS+<t*YA*tb<{cEn*{^RcrC=amI^=pous&6kVlDbQLu^3ZRN<hL~Q8HdofRO8p6j>#Cp-3|DR$$+}=p3^$UXBqxDBXYRMQ7i=hkG&UG+R0OF4hAS#$7hzZ{f)r#@iC^RI&#^fShlg3(tN+?w1j7aPRo3@P=+t01iPy0O!Uk&CO2#l-7M=>CCAwIio;XR_6~LU-f)ZQ)tS~@T+6S}h8<-A_P9F2!%=n0H401}OOLST>Dx@X4&={vgT8oZgcq}z#$SF}}vLgA04X>ji!SHx$$`A|}3M58F7}4eg!$v&^NHA=89SsSF4M&wB!LTW(MC=7ZvWC}Cf<hXn+SG#sDKQGfhX`A1BbzSW?KU-KSl`T|1j7Y}HRziimteTSu-1F^G_r<srM<GmEF^2#P-(9uWe5p|>u)CoRcLyDJd<$WBOSr8hLzcH*CR?04Cj-XquO5Ra0dy7$5GphtYOn+)&#?*YkLt48?Nm|FdQ}~hbP+iLDu#n7&cwoi(t5Jn{R^>R1$P|wY><2P1p7!7!GT5ZMF#dr;?!I&T4xR46or~>n>rkh8yMDY>|sZB|)3Oa7Aq|12BxV@=P#nYL3-YZ7-sIuRlxG_L`+h=0y7*4zsowS;K~Fdjatc*Pb<#smgOVFv>T~4%b|cYkT?IT5D7UsoolvwY}UG<2@8XI{1>Hm1nIOLtLyl-@YU$!EiMU$6G+O?}M)GMb@zC+FoQ0Z_quYlAvJ+YLAHiqzMlb$39Ae(hA<1I83C<%%-g2l_+)V!pdb-64Yo>nQe8LV7UG)9wjWI(aOw+Qj4zsEH^!Gn_6`1&f|w0H!Rg0y7H}25u}YO$x*5o%Ot!-5hQX-RL2cVO2&B_w?@9<-hIQODw6OGcZ^8M!7$WtBX6=7!y$&ECale~Xb)1y7$_%Mmq>}|Qm~4`;pa`1PH4XLj0#0YvW7Q1#E>E-!U5OzBHys-+Fs-vuGKv^S)6lx&u_1|z{xkfli+HC;U?=6NHA=cqu*{F-bzJ~c39hsV7Q41fCR&#(V{ZjR1+o`uJ;XV#b}VMVFNG>+ENk{44d#E7piZxga)d<(KwkIwqie+B*R+!KFT+l0Jy%UAi?m~4+{x~4bx~NS;JdxmkY-iOEN`*VZ+r7kgQ?DV`gUw6AU-hJtP=5TFs#QthqtlFdme?a$WbBM)!;a!`rT9Xcev@DZ`41jJo?Jns7?s;T1vRIZg?_1!o|^@Maoq*orfdtYOne7s0S;36nK!SX2bVjkh?CQsjXn!SIlDm|)nngb9Yj7LnTVh6KX{(qV#O(-I~a?vPbPFl;J+6n&AF1dNe2Y-D3G!!r;J8_T^#+$O7;Hbam~Fl<;_1jCItuUl;|g5frJ+C{<y!)>TVyJU_N3>y{~!LVrw6AYV{Fu`ye;X10CFy{orX52oVMmmDwR=kWIB2oy38*jcF_@0YMP6?ASR~=%02!@+(Hq0IFq1#eq1jB8*I|~DbK#>xrHn&q4HNkM34E-*(y$FU44_pMpZF_rL=1+p*u!Z+MTB#!#9u`Uv3>%g(!EkFPnwBU*Fx(tZF)UO(AsFs=Te_+MtuqS<hKGd11jD9ldl3wGn0Fw-u+bcSY$suY;SLB)=^H~D=?I3q%sjA#SP6zZ#b~#XFv0K^bGs%ICK&FrZA?^5s?DrIMljqlDy6Xw6AX8n*tL)_!Egt&D=lWVx%T^PMsnMRig^3V%(PWaGazgsVS?cfvtL{0HB)6~gPX%P*~79Hqstso>(3=|b#OxZ8zqcx!Z}DV+y#cyyyn`?Pv#j&Fx<ff*(x%SV7Mb%Ao+$3GCT+223rEiH@rPwAT7}uo;x>{Fu`!xE&OslN?>{-!EhHC7G>%-*uzLLye;{`dI>{TEs$Wii#05ywtmI|1jAb~$jk##^mgqk(oCHc&Z!oi`G^#P;qG{WWDT1ly4*~RJMTuFOIuzok(?5y;?%H(gb9Y5%U4k9#}$0U?p)33=Cxv-C$c3N?qUtQOs){|diDeH8HiJmb51baVbbixQp5)K1Ho_?7>*V;*UjlT!SFWW*fL;^uaB3YfVJ&r&k$~suv%kc<dkUVlt`@u2bc(!P&Dv$0_JWkXoBHR)-YGHUK6(l1jE}{Yl<%r*P;Xv3~v`Hp(2O*I*di~4R2u$^C%mXH_>5&;TH1M;wX6>@UvOM1jAimSWTEk)SpwA?G;y>;fyhY;SRoG<^Ul2%&x6D4m>6$27=)(108R%#7Qu`Wim68Z`eRAik8e=6Z1pK%)Kq?Z`NUg;VnxfBEhhMP2;DkMhVDHBpB`j!<uiMV{@~Ewho*UH4<joV;~srVhv|ft64=NPKoX8hb)4pCNhvXC3@55%_u-Hymi6wO*x??ucnF%Eb&`voDxykUx{3lI3>a!8P<@T5`CM)&;|wwhMOy{o5c8OoDxxF;EFgU`n4Z4P6-tm=n|(yFZM$$R?s;mK!v1~XLZCWu^kNOq*ghnLxSOL><0##{GbwPIa$M7DRa)}P|2Z<aZC_7B|5>dn=B%WNr+fb_R28fB>9P)V7QYt%=I^`A_FO4Z95pwG1RdzTsP7Y40kYxxgNV#Eny(v@HQ}vse~b{i3|jCN^Ie;gf{L;g5j-w!y6<_Fx+9F^NJspR`ZdT=z6Zcf#e%Dw?wx=!UV$|Hapye5<EMRV7LP`IOXhcq-5r>*D~XqB#h}}AQ<jq4VR==@(+`5INT;A&@L{?m12J8s7?~-j0D45#tm<>B?yN5szrxn4R0UI8h3aGC0egyV2{QS7Lerna7wJvVS?cfa^)=~Nif`k12;|X42t1BMK&-!Ym_9{!5ZdnL2gAhFiK|L&e>Cy!knMeQAyBF6XmQZj9<tZ5UPq8Xj2Q#>>$B)@K=`V?v!GFh}x&;lAt9COSy6&r$onza;YRJlveYpB<Ob5Fst}1AM=A`4R2!&muk@oLrsQaQ`~TGkrGgz%@rb2IQfRRv4%^ES(Y#o3~yr%7bRT528IN~TbL3)cT3Z`JR6uG)fQPaz6dKO7;e19MPY0N$i&SyGVK!#w?$zuR}yrygb9Y*NZ2ox1jU^6k$l5jZ1Kvms1Si!Nl*w9-*9{il>`m9UHP=raBK}_*XS_8@OCh~S;7Rv+f`<UJQN_o@Ycq#<Y3e)Gsmy1JPrdftZiovbLHsK){PP;4<a$Fg*`cd^5_6vqT*>=YYjtAeymoW1jAjdVG&GaN5NBZwB<Y^Q<^6sRm8Bir8S(va7<a1)Qd?9qfuq%juLjVNQp$IZm11(sf3B>vcqP}a?HvslVXIJ(jYP(ScC;4ECP{;E_;CC$o(FdOOyLNOL0bul;~^?XPYR~6)$^A<|MJ_GLY_esnFtoCrB6tfnd0^HC!aLtF_h$h8x51tlLJC>jJ~7R3gLye<B(p;_iqdDGDPU!EhHCj)DRq&Zk4=3SvpLYqZ?V$SKij&K!lRv8uYYyasm(hC9IUDxAxeqm@96m0UdnF+CP<*oz<n69!r(a*|xf*>f>osxHcsV7QfBHR8V_DAY-qV7M^~$G)<8sHPclN(^_!%pwrS;ti1VXqjgq=6K?L@eZb53fdY-ILay#Q#V<b8I^>&AMp)?lCaAKy|9?ex$_zE4R^7Ivw=<!U3yVU%pxMX47gyn6k03PSg5V|pNKAdSki}DGC(94-qtsq$&_!bPe(8uc3slvjdYl-;g%67ER!J5scxNw35J^sIPnE1)&b<?SBDY=!;QBnoL#uuA#(312YVU>uO}rfkdm3VjFeze_7)^B5UnFcb3T<QO0@6W!Em}Zr^E_Tt}UdvftYu~(bgJ<F_CG!7OGU4rMXCmj9_>x7*-3*$%=;3*(i%HUf%#c@0MWLFhdx@u=z3vw3(GK!Ek7BNt%c*cc8-r!=@!nFdQ0Qk`723hIN==*sz2NhC?$hA|krn$&xe?U52KMeldb!^ZeQ*48tQG!LVrw6AT;Kyo{8XU^q0i*u;>mVUwhoLdZxkyb~NI7&a|of?>lFCKxsspy{YA508Xl#_f}ibOgi3sP|*~eS%>lo9_m`=ep#S*iqIfZM|<c%pH+8;{(C4u{kqB48a7$W;Q2bp&=MHZ4?s>hXyNk01^zF8t5`AHiBWpC_yl6TEYawMqzj%;w4BLW@1qiqnKdW)N~^T2_zUcvn^d^Oe_`w!LaF(j$qjESV!p_rfoH%_Av?%kY<?EW^5hb`v1du?#2"
_ETP_CACHE = None


def _etp_tables():
    global _ETP_CACHE
    if _ETP_CACHE is None:
        import zlib as _z
        import base64 as _b
        raw = _z.decompress(_b.b85decode(_ETP_BLOB))
        cls = [raw[i] | (raw[_ETP_N + i] << 8) for i in range(_ETP_N)]
        _ETP_CACHE = (cls, raw[2 * _ETP_N:], max(cls) + 1)
    return _ETP_CACHE


_EQ_BLOB = b"c-obn(RCzAk|h6!iut@E;>e1&7G>Z_IR1{3+uiA|Mh4tX1wZ{}Dh+Ou8Ul^1L;?8o-~apHfBx&w|N1Zg^WQ)J{r~>&|M}}r{`0^8^XGi|bH4p~zRdrxzmE9z{m=OLGY)fH=kn{zzRw*Tc6|KV=f`sRSPmb1+MC12=J2t(e(e0`&wf9HFS&mH8DIa5!yNay|6GsX&-ClZa@g_lXCEKS;bS>`>}hWfADhF+=KitsufHPsu<`Fd`Nzr6KlwhBzy5^Z=Y0K>&vQ6_R6b7r=TGLl<-afEuj^wRA7lAA>c{2R;j`w<!ou?U#5q02awf}}8)ud?vz(cF=KMM|!Ydb+Yjk=n$H!RCWI2=N%q(YSIWzUlS1v5Mu;jv$3rj96xv=EIk_$^NEV*pHWXUB<E?IK<c<j87Wgp8vmVGSyvh2&UFU!6y&sp}(vTv4sQ};ceJ@L8;FOPA0jOF9#AD7R^SXfwCK5yQq$5_r}IdkL8a%Pq@)6blb>vz0HEZ6AxSWb_zoXK(~%b8iu%yMS>nXg<}a$(7ZB^Q=lSaM;>g(Vl3Tv&41e94kamRz#r^6}VlAIm<LeJuM}_GQ_ZWnY$kTb{G*n`PfD`=;-EPJdha{M+C0F^-S1d>r-T^6T(7ts@Hy%jaX~Gg;1LIdkL8a%Pq@Q_uYSZ?r7eh~*lc9?S7DmNQw-WH~d-nOV+EJ@YdcmRwkJVabIh7nWRDa$(7ZB^Q=lHea&jk|mccxqLo$-p8_!Wgp8vmVH_FW!aZy-<Ibr`)1iU%f6}mKKuHgzcqb-_v-Z+hsRhx4)JmMc#MUGh2`_H)0r%1vYfebW;rv<nGt8s*Xwt_Ml9Fp_*f2)v7E_rCd-*w&dhRV#F?MDu;jv$3rj96xv=EIk_$^NEV;1cviXuFmn^wt$>sC0(>|7cEc;mYvFyvTFU!6x`?fr1**D9+S@w<C_x$Iv_usO=vK$}d^cc&>(LXL9kFl_@uzWstJd@>2mNPfbEN5mpGyTlJuHXA_{2%*RuF>hSoE~F2ljTg7GqaqT<;?UmKXYNpg(Vl3Tv&2p$%Q2smRwkJVaa9lB}*<@a><g*=VQlxEc;mYvFu~nmt|j;eOdNxdCszLmVLAAo4)V)_7%~ue{(uM!r>9FA4B<={QCCQ)e`|%g706Me?7wWG_I%J*>XKC*V9r?n_u6)p8U>$>s9#nNDhy1J&o&WTu;mOv|LY1Iqf3@t{HI6fNKU^GvJy5*9^F3z%>J|8QeX{HG^C;$Tfp}dk5q72-iJa_i)|Abx*E)a@~{bo_lU{-80ucbKNs#&-3+j`}@DeIX}YpN4S0r?PK!w5v~MW3BLWSo!28=Pvd&poh{eXay>2WwE1#<&R2o!Rrvl$zCXhCG_I#{JuTPMay>2Ww2ut9X23NAt{HI6fNKU^GvJy5*9^F3aQ7hB406pN*9`K0rTTh=>mIIqxbES)C)Yi>?#Xq}J-4~;nd_dp?wPjdx&9lsf8HSc)n-^{5a*!J$*<+#(Cy3!=Jy+m%M4-{VwZVd5xXLGMemwl%fBnU<cx6R^3U;>8N@EcF2t^gT@kyYcU^Ku<c!D}kuxG^M9zqu5ji7rM&xXKj>tJ8=ZKu&|7>uXLGU1W5IhK;2%ZR@2p)62M(~W_8NoA}=lQk#o8z}*i2La>lXV8M3$Y8aD`Ho~uIOF!Yx#HBd(McQ5ji7rM&yjh8Idz0XGG43oFj6M$T=eCb7vlB5IhJT1P_8If+vC}g2!C15j-P!M(~X0d3PqFGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsn%9{Tof*-Y5uJIOnRN!igWy5%Ab28pB6uQrB6vpdjNlo;Gn(h(7{W1xV+h9(jv*XFIEHWx;TXa(gkuQD5RM@nLpX+T4B;5Uu?WW^9E)%)!m$X)A{>iwEW)t}$08hya4f>H2*)BEi*PK$F>|jR;n)brMmRRYv5%RZ8NrNTMld6o5zG<H5zG<H5zG<HBbY}pk6<3bY<zwM^COra!Tbp3M>GF%{+iVLA20VAwi(1Z_;YfeK`<kjU;k)!nL+GA>@v?QVpqhj_+4{+?|pRx;l|}#&6gR(F2pXxu83U`yW)3Uaz^Bg$Qh9{B4<R-h@25QBXUOMY<!N$IU?tXoL}D(zsw+b5IhJT1WyD{1WyEyxn3i9M(~W_8PD?^-+MoICgOg&&19QF>_Y59?26bGu`7Pp`R7xeI}`C50Pz|C@frZ}8UXPc0Pz|C@frZ}8UXPc;58GGb41P&IUhUoID_Cp@E~{)JP|w*JP|zRdX3;2!83wqJkN7{?|tn|L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaLGb!J3oMs#LGXC7x}n?dj(cn~}Yo(P@@o(P@@o)J7Fct-Gy=eanBa17xX!ZCzn2*(hPAsj<EhHwnw7{W1xV+h9(jv*XFIEHX6!m$X)A{>iwEW)t}$08hya4f>H2*)BEi*PK$u?WW^9E)(w+$%>oHo~zHj*W2aV`gPWFe8`|%m`)#a|Ck)a|Ck)a|H7U<`K*zm`5-hpC7^e2<AsHKZ5!3%ztb@XZrjz`7b}lbeln(gFYv}mY-F<G9#GZKgM#KLF_{8GS4ewSH!O9U9b1vFF!W5&md;9&LDOnb|H2}?26bGz3ZGaB4<R-h@25QBXUOMjK~?0Ga_f>b41P&IY;FD{&BC{41x#2gWy5%MDRrLMDUpFHG*dZ&j_B;Jg<B1dOt<nPq&$@Gl*S?U5H%~yCQZ)@0wrB?>ks?M&yjh8Idz0XGG43oDn%Aaz^AFk#j`O5jmeb^E`v#LGU1W5Ihk)5j+t*=6a3b8NoAxXEe{dGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB0AH&&Wz~Hh|Y}Y%+t)QGYB384}u556TuU~6TuU~GlFLX&j_B;JZHxcjv*XFIEHWx;TXa(gkuQD5RM@nLpX+T4B;5UF@$3X#}JN1I2PepgkuqoMK~7WScGE{jzu^Y;aG%Y5spPT7U5WgV-b#-d*uknMmRRYu@R1a&g{$xW&|^W8NrNTj$n>pj$n>pj$j_aJc4-y^9W|+^COra!Tbp3M=(E{`TVuW_pf~tGb}TRbNInIInE%M5zMb&(X`AUb|H3|=M}LlVpo2!YfkUI?`|O6IRA>UWd^Yeu?w*)Vpqhj{9xBPXGG43oDn%Aaz^Bg$Qh9{B4<R-#^;EfBXW+&`Sq*JmKg*Of(OBa;ECXg;ECWd*J}jN2%Zr<^8=pe^xpfqGZFXGbtcOUVi#f;Vpqhjh+X-?uH)~4KX)eLH2~r@0OB<O;xz!`H2~r@0OB<O;xz!`HNa~oBIk&lBXT}==5YqWgWy5%Ab28pB6uQr%=H?<GlFLX&-{SrIlcG3cP64U5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XO!GQ3qBA2pGomw(GqcPfcn~}Y9t2MWPXtc{PXx~ho)J7Fc;*K@XU7nZAsj<EhHwnw7{W1xV+h9(jv*XFIEHWx;TXa(gkuQD5ROGS7U5WgV-b!;I2PepgkuqoMK~7WScGE{jzu^Y;aG%Y5ssOA<p{?{I5xtu5srP%Y|IE|1T%se!Hi&zV2)spV2)spU>?Cdf_Vh<2xjB+BbXn-{0QbpFh4(F{^Rrg)%Q>NIKAI{oMD?moP$3n#~B1Og86f1-G$hN*kztq#IA^4@w;B{y}y4t$B_r&#%U(o3}P2z7h+e$u83XnyUsZyaz^Bg$Qh9{B4<R-h@25QBXTxAN8}ulb41RcGb;~*2f>5jLGVQIMDRrLnCmryX9Uj(p7A`dd+v5WMchx<nQSwNU5H(XT@kw?cE#_S;|wBaM9zqu5ji7rM&yjh8Idz0XGG2sIY;Cik@K-L&oc-f1P_7-!4ts~!4tt_uGa{j5j-P!#`C;86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qBG6w%!tm6=*)=DJk88DgWy5%Ab1cw5j+t*5j+t*BX~yejNlp1b9M~j7{W1xV+h9(jv*XFIEHWx;TXa(gkuQD5RM@nLpX+T4B=RWV-b!;I2PepgkuqoMK~7WScGE{jzu^Y;aG%Y5spPT7U7t=SB`LOgkvKd8{ydJ%*u>lMld6o5zGkY2<8ap2<8ap2<8#YBbY}pk6<=FKZ5xY%#UDx1oPvW|N2_w@rS^@zJGa}VVyyogFYwc83Z$enbY@NpJx!e5WCFtir5vgD|**_&LG@CxN)4xI)m7S*oD{?u`6O%^sY<Jh@25QBXUOMjK~?0Ga_e1&WN0i&k;FC<Q$Q6PCu*RJcHmt@E~{)JP|w*JP|zRdX3;2!83wqG|%5Zi{SVJ0^g1y?x)L4))~Yu#4g0Hh+Pr8qIb=C29Yx&XGG43oDn%Aaz^Bg$Qh9{BIk&lBXW+&`P`Yu83Yf42f>5jiQtLgiQqBUYXr{-o)J8wd0w4~=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%ndWt7L}x~HW<+NmXJ(y2@E~{)JP4i$o(P@@o(P^1JR^8U@QmiUIEHWx;TXa(gkuQD5RM@nLpX+T4B;5UF@$3X#}JMo978yUa4f>H2*)BEi*PK$u?WW^9E)%)!m$X)A{>iwEW)t}$08hyaLn8*M>saZu@R1qaBNOLqxC$4U`8+_m=Vkf<_P8p<_P8p<_P8y%p;gbFppq1K0ku_5zLQZegyNQng2L{P3rw^7=4Cq25}DloSbJ6%m`)<|IXn&gV=@GWu8~Wu83XnyXN@b`{oA1jq^;l8N@EcF2t^gT@kzDcU^Ku<c!D}kuxG^M9zqu5ji7rM&xXKj>tJ8=ZKth`1eug83Yf42f>5jiQtLgiQqBUYXr{-o)J9bd7k5Y@8`}$+)uZeY%_>mh+T+X5xXLG#qXN)3?gSl&WM~5IU{mL<c!D}kuxG^M9vX8N8}ul^RY9JGYB384}u556TuU~6TxGy*9e{wJR^9<^E}7*-nY&~bS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uIsXXGU~pL}x~H=6Pne83Yf42f>5jiQtLgiQtLg8NoAxX9Ul9o{M7$#}JMo978yUa17xX!ZCzn2*(hPAsj<EhHwnw7{W1xV+hA09E)%)!m$X)A{>iwEW)t}$08hya4f>H2*)BEi*PK$u?WY^y>f(OBODvy*a*kw@O_cz83Z$e8NrNTMleS(M=(b)M=(b)k6<3bJc4-yv+?;6%#UDx1oI=9AJ6>xeUYzU0`U9)_8Hb0#5w45a+*OfBbZ+^`!2*T#4hu^B6daWir)44-uvr^_n&h{xN)4xI)m7S*oD{?u`6O%^sZyhh@25QBXUOMjK~?0Ga_e1&WN0i&k;FC<Q$RnYi8#`@E~{)JP4i$o(P@@9&^1$@QmOY!84lY^PaokPZ9UiZ6@msVi#f;Vpqhjh+WaU<}`!I8Idz0XGG43oDn%Aaz^Bg$QhAyM9vX8N926z%<~L_2f>5jLGVQIMDRrLnCmryX9Uj(p3yw7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliReu8Iy0g(BRVspGmkT~&LDUYJO~~HPXtc{PXtc{&j_9oJR^8U^Bf&RIEHWx;TXa(gkuQD5RM@nLpX+T4B;5UF@$3X#}JMo978x3;aG%Y5spPT7U5WgV-b!;I2PepgkuqoMK~7WScGE{jzu_T?v*1P8{yap$3{5zn%S8V%m`)#GlChx9KjsH9KjsH9Kk$-c?9za<`K-s=SMI<g8325k6?Z@^WR^KJpMwe*XQXr!#aaF2YpVCGYDn`GskW@&meXocA4iDu`6O%^sf1wLAZf%<2aLb2C)mV3$ZI=SH!O9UFVz;IU{mL<c!D}kuxG^M9zqu5jh*5BXW+&IU?sAUz40?5IhJT1P_8If+vC}g2!C15j-P!M(~X0`TL%G{AFct#}N0^WhUzkVi#f;Vpqhjh+WaU<~W1M8Idz0XGG43oDn%Aaz^Bg$QhAyM9vX8N926z%;OA#2f>5jLGVQIMDRrLnCmryX9Uj(p3yw7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliReu8Iy0g(BRVspGmkT~&LDUYJO~~HPXtc{PXtc{&j_9oJR^8U^PC++IEHWx;TXa(gkuQD5RM@nLpX+T4B;5UF@$3X#}JMo978x3;aG%Y5spPT7U5WgV-b!;I2PepgkuqoMK~7WScGE{jzu_T?v*1P8{yap$3{3d$FD`6XAsN?W&|^W8NnRE9KjsH9KjsHJc4-y^9be<%*N+OFh7F%5zLQZel+v(`y&7OR)oJ^qKFypGl+Be$vHXAAea%%ubE{RVi#hUd0r8_B6j5`yXNqHK)V|VH_kJ;&meXob|H2}?26cxpX@s3jK~?0Ga_e1&WM~5IU{mL<c!GK_#BaQM9vX8zh)L51P_7-!Gqw5;ECXg;4#;01kVVb5j^t~p6Bp=K$p%$+)vk;+-DHG5W5h&B6daW%1?I9X$FxqB4<R-h@25QBXUOMjK~?0Ga~1RoFj6M$obrvoPW7f<w5Wucn~}hJP|w*Jmz|h;2FU)f@glh^BlepXzxr!XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V6CTW<+O3bY?_no@eGhgWy5%Ab1cw5j+t*5j+t*BX~yejNqA{@EjdOIEHWx;TXa(gkuQD5RM@nLpX+T4B;5UF@$3X#}JMo978x3;aG%Y5spPT7U5WgV-b!;I2PepgkuqoMK~7WScGE{jzu_T?v*1P8{yap$3{5znpv0;%m`)#GlChx9KjsH9KjsH9Kk$-c?9za<`K-s=SMI<g8325k6?a&!u-d_`>XG7M?AgXd!AvLL7c-6&dF&8!Hi&j&1}06yAZp~^NQFNu`55=_4(fW``c8GJP0?AGg)R3yAZn&yCQZ)?8*;z9dkzHjK~?0Ga_e1&WM~5IU{mL<ZOJ7$T=eCh@4+D8xMj9!GqvI@I>%L@I>&K>otOB1kVVb`2o-8J$JpIBJQW_OqLnMF2pXxu83U`yYhowbDBZqjK~?0Ga_e1&WM~5IU{mL<c!EUBIk&lBXT}>Cg)%7)Oip*2p$Aa1WyD{1dq91BX~yejNq9c@Vq(`(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGtKMFh|Y}Y%!tlB&df4{;6d;pcn~}hJP|w*JP|x2ct-Gy;F%xr934YAhHwnw7{W1xV+h9(jv*XFIEHWx;TXa(gkuQD5RM@nLpT=UScGE{jzu^Y;aG%Y5spPT7U5WgV-b!;I2PepgkuqoML1^el_MM*;n)brMmYAG*_aW`2xbH`f*HXa!5qOH!5qOH!90R_1oH^y5zNNtM=(Ev`4P;IV19nU{Kx5Mb-sQ_)1P97Wd?B$KR74H83Z$enNznMXArv(yUg>7*cGuWKiD;=pGmm7fpFtIlVt|63$Y8aD`Ho~uKZxvIcG%9h@25QBXUOMjK~?0Ga_e1&c^46oFj6M$T_FiB*z&94}u55gW!qaiQtLgG1qGZ&j_9oJo5vd=kzlPFP(|FpKdc*W)Qm&yAZn~c17&U4|dIQ29Yx&XGG43oDn%Aaz^Bg$Qh9{BIk&lBXW+&`P`Wtf1q0DLGU1W5Ihk)5j+t*=6a3b8NoAxXMVu*oPH+Z+L?&XM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGtKMFh|Y}Y%!tlB&&)D|;6d;pcn~}hJP|w*JP|x2ct-Gy;F%xroE<|rhHwnw7{W1xV+h9(jv*XFIEHWx;TXa(gkuQD5RM@nLpT=UScGE{jzu^Y;aG%Y5spPT7U5WgV-b!;I2PepgkuqoML1^el_MM*;n)brMmRR7uSFhb5X=Z>1T%se!5qOH!5qOH!5qOnf_Vh<2<8#Y#^*;cKZ5xY%#UDxe!%?swaE92+0*;I=NYyc#5wqLa+*OfBbZ+^>n_AD#4hu^B6daWir@A5-uwGS=#dBE#&IUw3}P2z7h+e$u83XnyN)>{az^Bg$Qh9{B4<R-h@25QBXTxAN8}ulb41RsnUx2@gWy5%Ab28pB6uQr%=H?<GlFLX&v>5Cd+vTeMchxfnQSwNU5H(XT@kw?cE#_S(+nbKM9zqu5ji7rM&yjh8Idz0XGG2sIY;Cik@KZ9k244!1P_7-!4ts~!4tt_uGa{j5j-P!#`C;76VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qBG6w%!tm6=*)=DJkHEEgWy5%Ab1cw5j+t*5j+t*BX~yejNlp1b94;h7{W1xV+h9(jv*XFIEHWx;TXa(gkuQD5RM@nLpX+T4B=RWV-b!;I2PepgkuqoMK~7WScGE{jzu^Y;aG%Y5spPT7U7t=SB`LOgkvKd8{yb%W@Sb&BbX7)2xbIx1aky)1aky)1oH^y5zHf)M=%?oAHn<x=0`9;g8A{xe}66V{ZrshpQqal+YI6y{5d(!Aea%%9J}Q>gV=@GWu8~Wu83XnyXJES;ReEu<4m?0#4f}x#IA^45xe4dopVOyjK~?0Ga_e1&WM~5IU{mL<ZOJ7$T=eCh@5kLO>&$;@E~{)JP4i$o(P@@9&^1$@QmOY!84xc?|bh1Cj=fHL)=f7nQSwNU5H(XT@kw?cE#_S;|wBaM9zqu5ji7rM&yjh8Idz0XGG2sIY;Cik@KZ9PcsM}1P_7-!4ts~!4tt_uGa{j5j-P!#`C;76VaK7&O~%3qB9YliRes3XCgWi(V2+OM06&iGZCGM=uAXsB03Y%nTXCrbS9!R5uJ(XOhjiQIup^Eh|WZGCZaPDor&m7L}wy86VaK7&O~%3qBG6w%!tm6=*)=DJkHEEgWy5%Ab1cw5j+t*5j+t*BX~yejNlp1b9M~j7{W1xV+h9(jv*XFIEHWx;TXa(gkuQD5RM@nLpX+T4B=RWV-b!;I2PepgkuqoMK~7WScGE{jzu^Y;aG%Y5spPT7U7t=SB`LOgkvKd8{ya-zZQ9%K`<kj5zGi?1aky)1aky)1ak!Q2<8#YBbY}p8=oJ+{0QbpFh7F%@y!4IwaEWr|F6l9?~(iG+Y!nH%LMfd<QX|lP)Vtz?|-m;ouF=^Zt2e@bxZ1&$Sw0RLB0CatACovGC|!!-9p`xx+Qf><d$Qm)J&<FQZuDyO3jp-DK%4SrqoQkr>U8yW}2F5UO&6$Izi>2a!@&_9H|_s9H|`rx=iJm$}yE=B**i6f_k5$-sf%;Sth7ks9UI8Qn#dTiQF=$32LU)OsSbtGo@xq&6JucHB)M))J#(|P0chl(@WERpP+J3Ij9^|j#Q3Rj#Q3*U8ZtO<(SGblH;@Ks7*(0I%?BVn~vIa)TX009kuDGO-F4yYSU4hj@oq8rlU3;wdtr$M{PQ4(@~p_+H};Wqc$D2>8MRdZ8~bxQJaq1bkwG!HXXI;s7*(0I%?BVo36j6OKrN;rb}(Q)5I(jR1PW!m4nKW%8|;E%8|-3m18Q$RF07xM}w#aQ4OLRL^X(N5Y-^6K~#gN22l;78bmdSY7o^RszFqPs0O7Plxk3_L8%6%8kA~KszIp+r5coKP^v+x2BjL5YEY^{sRs4C*i?h28Z_0QsRn&aY@}3DDk+teN=hY7B~2wwB~2wwC7nt-m2@iURMPJ0Q%Rpn`c%@Vl0K63kJDF1-rxMzCb&;f&%mCM(*%{2O8WYz!Pg1u7V4J%TvE5BZi(G8hj)vYt53c9$BEo0s9UI8s9RFEq;84ba?F&PDK%4SrqoQSnNl;QW=hSJnrZhmHPh5gQ!{=2`uOVvm4nJb<)Ct;a-?#ka`fvmm18Q$RF1J6&*9zTOVd&BbJvO7C#YMfTc}%7x1?@~-7=>MYNpgoshLtUrDjUal$t3uQ);HvOj9#W%``RBbJKmFpmI<-s2o&|RE|`RRE~aKrgBW>n94Dh<2k%ryfhuP>8MRdZ8~bxQJaq1bkwG!HXXI;s7*(0I%?BVn~vIa)TX009kuDGO-F4yYSU4hj@oq8rlU3;wdtr$M{PQ4(@~p_+H};Wqc$D2>8MRdZMy!NF16`Wn=ZBKjuUgApmI<-s2o&|RE|`RRE|`RsT@-|rgDtsI2uGXh-whkAgV!BgQx~k4Wb%EHHc~u)gY=tRD-AnQ4OLRL^UYYpj3lW4N5gA)u2>^QVmKqDAk};gHjDjH7M1fRD)6tN;Rn8#iklG)u5>cO*QCaVj-oHQc0<#R8lHwDrqWdDrqWdD(O_xsiad$r;>J0pGx{v(x;L>mGrTse|&wv@bkso@Bh~(SSF}vAkWBQf=WsyegEqE`vi3hbxVIPsasOFL~i+bxA^mg*fCS;)jv&SnV@c=ZlP{T-IBT`a?2@GYNpgoshLtUrDjUal$t3uQ);H&)6`5;GfmC({fo-)6I2c=2bF`$k;;+Ek;>7p%T$i398)<)a(vtg_xl|6K6jnSGC|!!-9p`xx+Qf><d!*1P&1`wO3jp-DK%4SrqoQSnNl;QW}2F5YNn}~UYhPOLFJ%wP&ud^sT`>ssT}>fOy!u$F_mK^$7j<~n~vIa)TX009kuDGO-F4yYSU4hj@oq8rlU3;wdtr$M{PQ4(@~p_+H};Wqc$D2>8MRdZ8~bxQJaq1bkwG!HXXI;s7*(0I%?BVn~vIa)TX00U4KoN+H|Q+m)dlviCHG798?Y}2bCk0Bb6hSBb8$+$5f7~93weS22l;78bmdSY7o^RszFqPs0L9Dq8dash-whkAgV!BgQx~k4N5gA)u2>^QVmKqDAk};gHjDjH7M1fRD)6tN;N3epj3lW4eEEXsRm6oXsSU|4f>qeNU5Y$QYtBxluDXPno62Vno62VI+b)P=~U9Gq}|h}l0KF6siaROeI)7Wt6u+nXXWpo+qh3~ouHn9J|l+-Dk+up^-I#P6Vxr#E&aKqZb{t|y=A_?TfAL;>eW9^<T^p!Lft~$lDZ{zOZ1jgrqoQSnNl;QW=hSJnkh9?YNpgoyQis{re>O&>FZZwUni&>R1PW!l_QlSl_Qm-Uze#IQ#qz`jOKX0zgv81I_iDyK9TDLbqjS1bxZ1&)Gg6l<}g9cl$t3uQ);HvOsSbtGo@xq&6JvHYNn}~re=C>y6+QI4k`zggUXT0k;;+E(XY!?j;S0|IYx6l-`_3XnvU9Z)TX009kuDGO-F4yYSU4hj@oq8rlU3;wdtr$M{PQ4(@~p_+H};Wqc$D2>8MRdZ8~bxQJaq1bkwG!HXXI;s7*(0I%?BVn~vIa)TX00U4KoN+H|Q+m)dm4iMdWtIj9^|4k||~M=D1uM=Hluj;S0|IYx7w45AuDHHc~u)gY=tRD-AnQ4OLRL^X(N5Y-^6K~#gN22l;78kA~KszIp+r5coKP^v+x2BjL5YEY^{sRpGQlxk3_L8%6%8r1J%Qw^GG&{Tt_8uU4FC#8~7NvWh%QYvXGX)0+dX)0+d=~U9Gq*F<!l6Fs@O8QjNr;<LE^wFeWf3MfKpAYc;eaqtn_X+A5*fVmNppsHazyGe&%LH``bxVIPsasOF#BTX`xA^_N{Ra-})#vg%iZ2t?Ez~X4EvZ{lx5REaWlGJInkh9?YNpgoshLtUrDjUaw0oMGX=<janSTEbw3i7g2bF`$LFGv0NaaZ7=+|W`$5f7~9Ah~??u6@oj(VTFPvky9-9p_$-IBT`bxZ7)IZRM9rDjUal$t3uQ);HvOsSbtGo@ylnrUjLshOUe?l3{+pmI<-s2r&rsT`>s{klx$n94DgV=TvK(@~p_+H};Wqc$D2>8MRdZ8~bxQJaq1bkwG!HXXI;s7*(0I%?BVn~vIa)TX009kuDGO-F4yYSU4hj@oq8rlU3;wdtr$M{PQ4(@~p_+H};Wqc&ZCO_$nqsZE#Kbf<~APf$6i98?Y}M=D1uM=D1u$5f7~98)>Qa-0mJ8bmdSY7o^RszFqPs0L9Dq8dash-whkAgV!BgQx~k4Wb&9YEY^{sRpGQlxk3_L8%6%8kA~KszIp+r5coKP^v+x2BjL*?_yI8nrhHggQgnvIkAvZNvWh%QYtBxG?g@!G?g@!G?jEJ=~U9Gq*F<|r%xq)D(O>6pGx{z(!amz_0QW{uist&`@7N(6R+=UyiW8pa+=`yeV*3|>cqB%x`n!>KbO=ksaqnq%xi*g*EY+<IS=Z!rC!^w6RBHLw?u9^=CL|Pb&Tp5)iJ6;RD-AnQ4PWwl$uy-VyTJc_}$ls2`UGbgUUhWNZryio%&p+ZkhUAMsocAPT_yv2)usoQ+xgU#M|WC1a+csnbXAObDw&Dq26Dp%};H9YV%W@|I0+`vrT=rm(R-Y6Vxr#EsH^y&&ux;Q#qz`OywBK@&1gWe!fsY8>pWR)XxU$X9LxBs_RsfsU}lBrFu&Bl<FzfLaK#S3#pFv*3LJ_W|=rUmTJ(~iSy^n_lYCv>e%;*StiaFraJa@V(J-FNtb84TA1oss$;2+#ThhPOMRc%&R86q<4=D%Ogxq2^|MUA{w?YC4_4{~_X+A5*fVmPppsHaIlcRJn4oT<Zt2e@bxZ1&*e!E-jk{ib>eW9?<UT>&Lft~$lDZ{zOYD|orqoQSnNl;QW=hSJnkh9?YNpgoyQis{re>O&X-@BaA10_AR1PW!l_QlSl_Qm-Uze#IQ#qz`jOBO^fA_dF9rZqUoydKHx`n!hx+Qf>>Xz6obDE%LO3jp-DK%4SrqoQSnNl;QW=hR8HPh5gQ!_m`-S-J92bF`$LFGv0NaaZ7=+|W`$5f7~9Ai12!{30{rlU3;wdtr$M{PQ4(@~p_+H};Wqc$D2>8MRdZ8~bxQJaq1bkwG!HXXI;s7*(0I%?BVn~vIa)TX009kuDGO-F4yYSU4hj@oq8rlU3;wdtr$*I(16HeG7dr8eDRV(t@E4k`zggUXT0k;;+Ek;*ZZV=Bi~j<Fm^gQx~k4Wb%EHHc~u)gY=tRD-AnQ4OLRL^X(N5Y-^6K~#gN2BjL5YEY^{sRpGQlxk3_L8%6%8kA~KszIp+r5coKP^v+x2KBqxRD-4(G}WM~2F>YTbsi?Dq*PKWDV3B;no62Vno62Vno2sAbSmjo(y64~)2EU?mGr5kPbGaU=^y`ky-qy5F1$|scD+sXGjf`Ez5Zwu)QM#abqjS%e=ez8Qn$oznb!n|SM=A3OCHo~OTD%nUX8a2>O|ji%wu(o>KN5As$*1xs0L9Dq8fxVC^fOv#8MM`y{5ZPP&ud^R1PXf>Xx4A)aNpF%hcyGmgD)?s|)U*`_x|lKJhmBIzgT2Tjn%z{@kbDU#RyNYV%W@pW6J?=Kng8`fO95?fJ9v`vi3hb<1YZ`Lpu-#8i%{98)>Qa=bsIsGl#?&j#ve1NF0k`q@Bro$5N(WU9$jPpO_#J*9d|wUBBd)k3Ocy|r_Acl0`OaV*uK9Nv{|6Gzh3u^iqnyiQy!Om!@W_t@G*>csKct`?>`mg-olV{rz})>1jV?{J;i9DBVZaGiK6$KQXy{r^=$i|P"
_POOL_BLOB = b"c-oCvTax2A4Eyi1<U^FG*WCYLYXKnbOea%YscJit_yR$SY5!AR=hI$>PkU8-&i8uOfBZUOSo!k2P8f7peyTo4-=#56v|lGGP8=N#8VkP1i4yylj{c`Wqw9oY*Wt10JuDQg`kRa^x`OvAe~UCkJRw709J2n~Uwk}1l5xcw@0RbL?{TWU$=v(5be_ERK!&l`e3pE+d|Ey!<H}f5#DQB8(k=_1WNzPxpX;RKY-kCYCaf&85i+-L!JK!QJ91Y(o1!d<N8lD&ubIJ{2X{_m#ouIZ?pQL&wNu`B5MKEMw>vAIm;~|$nTX@Yz?H+AmWnKS%KVMdCoG@1Wv*WTlM#@)J*rtNEh|UbZ`+s5zazg9dSY<<kx{1Q`jF1-LdM0~s(jyl=C)fEXMvp$Z2vbJkZH<$;A0OvO;MKQNc&mp2lHAR*J_uC{rYBDj|@-j4LnWS2VxyKb@X(s8J<VaOuOS+o6vKfL(IJN$b)0=oSo_z=RA>|@}xl0728zbqn`uo$FqjLu1E*`q~(T_>{ktXkDkj8JQ#?zzjY_d4M;K;V%_!Ea%bv|tCX#XqRBQj#ZJ$xLGow+2`(Kh7fv;uU05S;2cjev3-O(2OJ*Ng#vlD{AX3MA$9MYAj4pg{utIIb&mR%d=OrH<XI5q%dx&hlB9A9)3*TL+7I9!9?j`Hw@sVKE4j+Tt4H@dNw4i$_o&sycFfs$A(#Me)&ScIICQJGPp+IZM23gdFL6NQs4Nce)uLTcHsEw@4C7ngJuw>_)DCy%Aj$}UTYd|wIIUc$fP@CCfx-=J9BhRX8V&Hs-epcDSUU)OG>*@<U)gMeL4;-ghzOn|Za?Pl^7}tbu@XNIBS<y?f9bPYBMT;$CX<DC<ZbFpZW~s9zo6^UXdb+x57XvEvO!d|V>!!Wv5(c@Ieba$_^tzS^TQZ+WR%x8tDd|U*zB|`FtGekvF5p`gj_eXE?~blY@9G;%ENYJoSLL$G)<i@lI~27pb^4wRslqmKl8*~fL_VTsOdZ0LS4~;B)E#xfyP@iCpuVXdT@~?4uU(PFJ$bW|n9R(-3CHM%Q#lWAGat<CgqIfmAgj+66ZgAvO7^$RgeeD0H$zjTflM%`2}RGz@!TSxee7AeLwzl}ilvY2I-a->^+A(t_-I1LRSzYRH~CMyO$?o4L9z-yuAB$DGB&e*?^|N2%3}uQjT^kG*_Ueejgei2oqK7f=&z{LyT0RI=6rtF)#0Pr<1#eR!jAPFNW<E-v_+t%G7t!7!!^U8t_wtYaZHu06?nAeM^$Dv%rV2J*3VpQ<!lPM&HbX*?eyTxgj>^JaG*c#Hj9h!9NMBJTk0YlCE|}uX~Iq8gbY3wk=)_d676?3Sql_`k5+VMMOa1iN!(UjTx$V!Q9;*?Z%2IW;g&rXrlPoZCcaZyOeKP*D_R;>YKnR@YAxcw8|GmAU7d5P(_)GCw$R|^Fv2qHZ}aTRL7_zQNV4@dV@{skk%5vmv~{ajq)vHgIi^yPmF&MeE1gr$4yWufrmcGvr@|faTT%EuNg#LPa@xAI8s43NEd5@Xuvj$j82xn(bx!SDGYC6+*S*qc#R1&PK`{816;^X1A#snH_?@tI`w#v1VQDrHEmgvT#d&RzTZ{3Fv^%F4Q{j%+ug&L?$L0qGcXR!<SwCyvpSAbT+U>LU^;x@r)c%k7zv%hm%$JD1!14v#&pv(&^b1;FApe}VA8XnF`?LSqMY8y>h#9Q8u4Ch5i6&_{QKNHjP5M)FtFfc)b8e7yyoO0yviw+sXO_SJJepOf4YaSSAAjiGM*BEgQ7W8UkJy0g_L!)x;0OjW-mMm68-8+`oWPB0Y_zCz_Aq+SUjWooqjfno@m?v>laP9gW;irWqS0^=ymsn;wxsaO"
_EQ_CACHE = None
_POOL_CACHE = None


def etp_equation(i):
    """Text of ETP equation i, 1-based, operator already the diamond."""
    global _EQ_CACHE
    if _EQ_CACHE is None:
        import zlib as _z
        import base64 as _b
        text = _z.decompress(_b.b85decode(_EQ_BLOB)).decode("utf-8")
        _EQ_CACHE = text.split(chr(10))
    return _EQ_CACHE[i - 1] if 1 <= i <= len(_EQ_CACHE) else None


def magma_pool():
    """Curated finite magmas from the project data. They refute implications
    whose smallest counterexample is larger than any local search reaches."""
    global _POOL_CACHE
    if _POOL_CACHE is None:
        import zlib as _z
        import base64 as _b
        _POOL_CACHE = []
        text = _z.decompress(_b.b85decode(_POOL_BLOB)).decode()
        for line in text.split(chr(10)):
            if not line:
                continue
            head, _, rest = line.partition(":")
            n = int(head)
            flat = [int(v) for v in rest.split(",")]
            _POOL_CACHE.append((n, [flat[i * n:(i + 1) * n] for i in range(n)]))
    return _POOL_CACHE


def problem_ids(problem):
    """The two equation numbers of a problem, or None."""
    ids = []
    for key in ("eq1_id", "equation1_id", "eq2_id", "equation2_id"):
        val = problem.get(key)
        if val is None:
            continue
        m = re.search(r"(\d+)", str(val))
        if m:
            ids.append(int(m.group(1)))
    if len(ids) < 2:
        return None
    return ids[0], ids[-1]


def etp_verdict(problem):
    """0 unknown, 1 true, 2 false, 3 conjectured false, for 1-based ids."""
    try:
        pair = problem_ids(problem)
        if pair is None:
            return 0
        a, b = pair
        if not (1 <= a <= _ETP_N and 1 <= b <= _ETP_N):
            return 0
        cls, packed, ncls = _etp_tables()
        pos = cls[a - 1] * ncls + cls[b - 1]
        return (packed[pos >> 2] >> ((pos & 3) * 2)) & 3
    except Exception:
        return 0



def normalize(text):
    """Problem statements sometimes write the operator as * or a lookalike
    glyph; the rules call it a display convention. Everything becomes the
    canonical diamond before parsing, so no spelling can crash the solver."""
    for alias in ("*", "⋄", "∘", "·"):
        text = text.replace(alias, OP)
    return text


# -- equation parsing ------------------------------------------------------

def parse_side(s, variables):
    s = s.strip()
    while len(s) >= 2 and s[0] == "(" and s[-1] == ")":
        depth = 0
        wraps = True
        for i, c in enumerate(s):
            depth += (c == "(") - (c == ")")
            if depth == 0 and i < len(s) - 1:
                wraps = False
                break
        if wraps:
            s = s[1:-1].strip()
        else:
            break

    depth = 0
    split_at = -1
    for i, c in enumerate(s):
        depth += (c == "(") - (c == ")")
        if depth == 0 and c == OP:
            split_at = i
    if split_at >= 0:
        left = parse_side(s[:split_at], variables)
        right = parse_side(s[split_at + 1:], variables)
        return lambda env, l=left, r=right: env["op"](l(env), r(env))

    if len(s) == 1 and s in variables:
        return lambda env, v=s: env[v]
    raise ValueError("cannot parse: " + repr(s))


def parse_equation(text):
    seen, variables = set(), []
    for v in re.findall(r"\b([a-z])\b", text):
        if v not in seen:
            seen.add(v)
            variables.append(v)
    lhs, rhs = text.split("=", 1)
    return variables, parse_side(lhs, seen), parse_side(rhs, seen)


def holds(triple, n, op):
    variables, lhs, rhs = triple
    for vals in product(range(n), repeat=len(variables)):
        env = {"op": op}
        env.update(zip(variables, vals))
        if lhs(env) != rhs(env):
            return False
    return True


def violated(triple, n, op):
    variables, lhs, rhs = triple
    for vals in product(range(n), repeat=len(variables)):
        env = {"op": op}
        env.update(zip(variables, vals))
        if lhs(env) != rhs(env):
            return True
    return False


# -- counterexample search -------------------------------------------------

def _witness(eq1, eq2, n, table):
    op = lambda a, b, t=table: t[a][b]
    return holds(eq1, n, op) and violated(eq2, n, op)


def search_exhaustive(eq1, eq2, n):
    for enc in range(n ** (n * n)):
        table = [[(enc // n ** (i * n + j)) % n for j in range(n)] for i in range(n)]
        if _witness(eq1, eq2, n, table):
            return table
    return None


def search_backtrack(eq1, eq2, n, deadline):
    variables, lhs, rhs = eq1
    cells = [(i, j) for i in range(n) for j in range(n)]
    table = [[None] * n for _ in range(n)]

    def eval_partial(fn, env):
        def op(a, b):
            if a is None or b is None or table[a][b] is None:
                raise KeyError
            return table[a][b]
        env2 = dict(env)
        env2["op"] = op
        try:
            return fn(env2)
        except KeyError:
            return None

    def hyp_ok():
        for vals in product(range(n), repeat=len(variables)):
            env = dict(zip(variables, vals))
            lv, rv = eval_partial(lhs, env), eval_partial(rhs, env)
            if lv is not None and rv is not None and lv != rv:
                return False
        return True

    def recurse(k):
        if time.monotonic() > deadline:
            return None
        if k == len(cells):
            full = [row[:] for row in table]
            return full if _witness(eq1, eq2, n, full) else None
        i, j = cells[k]
        for v in range(n):
            table[i][j] = v
            if hyp_ok():
                got = recurse(k + 1)
                if got is not None:
                    return got
        table[i][j] = None
        return None

    return recurse(0)


def search_affine(eq1, eq2, max_n):
    """Affine magmas a ◇ b = (p·a + q·b + s) mod n. The space is only n³ per
    order, yet these linear models witness a large share of the known false
    implications, reaching orders far beyond exhaustive table search."""
    max_vars = max(len(eq1[0]), len(eq2[0]))
    for n in range(2, max_n + 1):
        if n ** max_vars > 300_000:
            break
        for p in range(n):
            for q in range(n):
                for s in range(n):
                    op = lambda a, b, p=p, q=q, s=s, n=n: (p * a + q * b + s) % n
                    if holds(eq1, n, op) and violated(eq2, n, op):
                        table = [[op(a, b) for b in range(n)] for a in range(n)]
                        return n, table
    return None, None


def search_random(eq1, eq2, n, deadline, samples):
    """Random tables on Fin n with a cheap reject: most tables die on the
    first hypothesis tuple checked, so millions of candidates are affordable."""
    randint = random.randint
    for _ in range(samples):
        if time.monotonic() > deadline:
            return None
        table = [[randint(0, n - 1) for _ in range(n)] for _ in range(n)]
        op = lambda a, b, t=table: t[a][b]
        if holds(eq1, n, op) and violated(eq2, n, op):
            return table
    return None


def pool_counterexample(eq1, eq2):
    """Try the curated magmas before any search. Each is checked exactly the
    same way as a searched table, so a hit is a verified certificate."""
    for n, table in magma_pool():
        op = table.__getitem__
        try:
            if holds(eq1, n, lambda a, b, t=table: t[a][b]) and \
                    violated(eq2, n, lambda a, b, t=table: t[a][b]):
                return n, table
        except Exception:
            continue
    return None, None


def find_counterexample(eq1, eq2, budget_s):
    deadline = time.monotonic() + budget_s
    for n in (2, 3):
        table = search_exhaustive(eq1, eq2, n)
        if table is not None:
            return n, table

    n, table = search_affine(eq1, eq2, max_n=8)
    if n is not None:
        return n, table

    if time.monotonic() < deadline:
        table = search_backtrack(eq1, eq2, 4, deadline)
        if table is not None:
            return 4, table

    for n in (5, 6):
        if time.monotonic() >= deadline:
            break
        table = search_random(eq1, eq2, n, deadline, samples=400_000)
        if table is not None:
            return n, table
    return None, None


# -- Lean code generation (matches the judge contract) ---------------------

def make_false_code(n, table):
    return (
        "import JudgeProblem\n"
        "import JudgeDecide.DecideBang\n"
        "import JudgeFinOp.MemoFinOp\n"
        "open MemoFinOp\n\n"
        "def submission : Goal := by\n"
        f"  let m : Magma (Fin {n}) := {{\n"
        f"    op := finOpTable \"{json.dumps(table)}\"\n"
        "  }\n"
        f"  refine ⟨Fin {n}, m, ?_⟩\n"
        "  decideFin!\n"
    )


def make_true_code(proof_body):
    body = "\n".join("  " + l if l.strip() else "" for l in proof_body.strip().split("\n"))
    return "import JudgeProblem\n\ndef submission : Goal := by\n  intro G _ h\n" + body + "\n"


# -- deterministic collapse proof ------------------------------------------

def _ordered_vars(text):
    seen, out = set(), []
    for v in re.findall(r"\b([a-z])\b", text):
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def collapse_proof(eq1_text, eq2_text):
    """If the hypothesis has the form x = <expr without x>, every two elements
    are equal and any goal follows. Returns a proof body, or None."""
    lhs, rhs = (p.strip() for p in eq1_text.split("=", 1))
    if lhs != "x" or "x" in set(re.findall(r"\b([a-z])\b", rhs)):
        return None
    filler = " ".join(["a"] * (len(_ordered_vars(eq1_text)) - 1))
    g_lhs, g_rhs = (p.strip() for p in eq2_text.split("=", 1))
    return (
        f"intro {' '.join(_ordered_vars(eq2_text))}\n"
        f"have all_eq : ∀ (a b : G), a = b := "
        f"fun a b => (h a {filler}).trans (h b {filler}).symm\n"
        f"exact all_eq ({g_lhs}) ({g_rhs})"
    )


# -- rewrite prover for true implications ----------------------------------
#
# Simulates Lean's rw tactic exactly: instantiating the hypothesis gives a
# closed equation, and rw replaces every occurrence of its left side in the
# goal. A breadth-first search over short chains of such rewrites (forward
# and backward) closes many true implications outright, and the found chain
# is emitted verbatim as `intro ...; rw [h a b, ← h c d, ...]`.

def parse_tree(s, variables):
    """One side of an equation as a tree: a variable name, or ('.', l, r)."""
    s = s.strip()
    while len(s) >= 2 and s[0] == "(" and s[-1] == ")":
        depth = 0
        wraps = True
        for i, c in enumerate(s):
            depth += (c == "(") - (c == ")")
            if depth == 0 and i < len(s) - 1:
                wraps = False
                break
        if wraps:
            s = s[1:-1].strip()
        else:
            break
    depth = 0
    split_at = -1
    for i, c in enumerate(s):
        depth += (c == "(") - (c == ")")
        if depth == 0 and c == OP:
            split_at = i
    if split_at >= 0:
        return (".", parse_tree(s[:split_at], variables),
                parse_tree(s[split_at + 1:], variables))
    if len(s) == 1 and s in variables:
        return s
    raise ValueError("cannot parse: " + repr(s))


def tree_equation(text):
    seen = set()
    order = []
    for v in re.findall(r"\b([a-z])\b", text):
        if v not in seen:
            seen.add(v)
            order.append(v)
    lhs, rhs = text.split("=", 1)
    return order, parse_tree(lhs, seen), parse_tree(rhs, seen)


def subterms(t):
    yield t
    if isinstance(t, tuple):
        yield from subterms(t[1])
        yield from subterms(t[2])


def match(pattern, term, sigma):
    """Bind pattern variables (h's variables) against a ground term."""
    if isinstance(pattern, str):
        if pattern in sigma:
            return sigma[pattern] == term
        sigma[pattern] = term
        return True
    if not isinstance(term, tuple):
        return False
    return match(pattern[1], term[1], sigma) and match(pattern[2], term[2], sigma)


def subst(pattern, sigma):
    if isinstance(pattern, str):
        return sigma[pattern]
    return (".", subst(pattern[1], sigma), subst(pattern[2], sigma))


def rewrite_all(t, frm, to):
    if t == frm:
        return to
    if isinstance(t, tuple):
        return (".", rewrite_all(t[1], frm, to), rewrite_all(t[2], frm, to))
    return t


def render(t):
    if isinstance(t, str):
        return t
    return f"({render(t[1])} {OP} {render(t[2])})"


def build_rule(name, text):
    v, lhs, rhs = tree_equation(text)
    return (name, v, lhs, rhs)


def rewrite_prove(eq1_text, eq2_text, budget_s=45, max_depth=5, max_nodes=20000):
    """Search for a rw chain from the goal to closure using the hypothesis
    alone. Two passes: goal-variable fills first, compound subterm fills on
    the remaining budget."""
    rules = [build_rule("h", eq1_text)]
    deadline = time.monotonic() + budget_s
    found = _rewrite_search(rules, eq2_text, deadline - budget_s * 0.55,
                            max_depth, max_nodes, compound_fills=False)
    if found is None and time.monotonic() < deadline:
        found = _rewrite_search(rules, eq2_text, deadline,
                                max_depth, max_nodes, compound_fills=True)
    if found is None:
        return None
    g_vars, steps = found
    intro = f"intro {' '.join(g_vars)}\n" if g_vars else ""
    return intro + ("rfl" if not steps else f"rw [{', '.join(steps)}]")


def _rewrite_search(rules, goal_text, deadline, max_depth, max_nodes,
                    compound_fills):
    """Core BFS over rw chains drawn from several rules. Returns
    (goal_vars, steps) with steps referencing each rule by name, or None."""
    g_vars, g_lhs, g_rhs = tree_equation(goal_text)

    def moves(goal):
        out = []
        fill_pool = list(g_vars)
        if compound_fills:
            for side in goal:
                for u in subterms(side):
                    if isinstance(u, tuple) and u not in fill_pool:
                        fill_pool.append(u)
            fill_pool = fill_pool[:10]

        for name, r_vars, r_lhs, r_rhs in rules:
            for arrow, pat, rep in (("", r_lhs, r_rhs), ("← ", r_rhs, r_lhs)):
                pat_vars = {v for v in subterms(pat) if isinstance(v, str)}
                free = [v for v in r_vars if v not in pat_vars]
                if len(free) > 2:
                    continue
                for side in goal:
                    for u in subterms(side):
                        sigma = {}
                        if not match(pat, u, sigma):
                            continue
                        for fills in product(fill_pool, repeat=len(free)):
                            s2 = dict(sigma)
                            for v, fill in zip(free, fills):
                                s2[v] = fill
                            frm = subst(pat, s2)
                            to = subst(rep, s2)
                            if frm == to:
                                continue
                            new_goal = (rewrite_all(goal[0], frm, to),
                                        rewrite_all(goal[1], frm, to))
                            if new_goal != goal:
                                args = " ".join(render(s2[v]) for v in r_vars)
                                out.append((f"{arrow}{name} {args}".rstrip(),
                                            new_goal))
        return out

    start = (g_lhs, g_rhs)
    if start[0] == start[1]:
        return g_vars, []

    frontier = [(start, [])]
    visited = {repr(start)}
    for _ in range(max_depth):
        next_frontier = []
        for goal, path in frontier:
            if time.monotonic() > deadline or len(visited) > max_nodes:
                return None
            for step, new_goal in moves(goal):
                key = repr(new_goal)
                if key in visited:
                    continue
                visited.add(key)
                new_path = path + [step]
                if new_goal[0] == new_goal[1]:
                    return g_vars, new_path
                next_frontier.append((new_goal, new_path))
        frontier = next_frontier
        if not frontier:
            return None
    return None


# Fresh names for derived-lemma variables; they never collide with the
# goal's x..v because each have-lemma binds its own scope anyway.
LEMMA_VARS = "abcdefgh"


def derive_lemmas(h_rule, budget_s, limit=10):
    """Saturate small consequences of h: rewrite either side of h with an
    instance of h itself, keep the resulting equations that our own engine
    can prove from h in a few steps, and return them with their proofs.
    These are the stepping stones the direct chain search cannot see."""
    _, h_vars, h_lhs, h_rhs = h_rule
    deadline = time.monotonic() + budget_s

    def renamed(pair):
        order = []
        def walk(t):
            if isinstance(t, str):
                if t not in order:
                    order.append(t)
            else:
                walk(t[1]); walk(t[2])
        walk(pair[0]); walk(pair[1])
        mapping = {v: LEMMA_VARS[i] for i, v in enumerate(order)}
        def rename(t):
            if isinstance(t, str):
                return mapping[t]
            return (".", rename(t[1]), rename(t[2]))
        return rename(pair[0]), rename(pair[1])

    seen = set()
    candidates = []
    base = (h_lhs, h_rhs)
    for side_idx in (0, 1):
        for pat, rep in ((h_lhs, h_rhs), (h_rhs, h_lhs)):
            pat_vars = {v for v in subterms(pat) if isinstance(v, str)}
            free = [v for v in h_vars if v not in pat_vars]
            if len(free) > 1:
                continue
            for u in subterms(base[side_idx]):
                sigma = {}
                if not match(pat, u, sigma):
                    continue
                for fills in product(h_vars, repeat=len(free)):
                    s2 = dict(sigma)
                    for v, fill in zip(free, fills):
                        s2[v] = fill
                    new_side = rewrite_all(base[side_idx], subst(pat, s2),
                                           subst(rep, s2))
                    pair = ((new_side, base[1]) if side_idx == 0
                            else (base[0], new_side))
                    if pair[0] == pair[1]:
                        continue
                    if sum(1 for _ in subterms(pair[0])) > 11 or \
                       sum(1 for _ in subterms(pair[1])) > 11:
                        continue
                    pair = renamed(pair)
                    key = repr(pair)
                    if key not in seen:
                        seen.add(key)
                        candidates.append(pair)

    lemmas = []
    for i, (lhs, rhs) in enumerate(candidates):
        if len(lemmas) >= limit or time.monotonic() > deadline:
            break
        lemma_vars = sorted({v for t in (lhs, rhs)
                             for v in subterms(t) if isinstance(v, str)},
                            key=LEMMA_VARS.index)
        goal_text = f"{render(lhs)} = {render(rhs)}"
        found = _rewrite_search([h_rule], goal_text,
                                time.monotonic() + 1.5, 3, 4000,
                                compound_fills=False)
        if found is None:
            continue
        _, steps = found
        if not steps:
            continue
        name = f"d{len(lemmas) + 1}"
        proof = f"intro {' '.join(lemma_vars)}\nrw [{', '.join(steps)}]"
        lemmas.append(((name, lemma_vars, lhs, rhs), proof))
    return lemmas


def lemma_prove(eq1_text, eq2_text, budget_s=120):
    """The stronger true prover: saturate derived lemmas from h, then search
    the goal over h plus the lemmas, emitting have blocks for the lemmas the
    chain actually uses."""
    h_rule = build_rule("h", eq1_text)
    deadline = time.monotonic() + budget_s
    lemmas = derive_lemmas(h_rule, budget_s=min(20.0, budget_s * 0.2))
    if not lemmas:
        return None
    rules = [h_rule] + [rule for rule, _ in lemmas]

    found = _rewrite_search(rules, eq2_text,
                            deadline - (deadline - time.monotonic()) * 0.5,
                            5, 40000, compound_fills=False)
    if found is None and time.monotonic() < deadline:
        found = _rewrite_search(rules, eq2_text, deadline, 5, 40000,
                                compound_fills=True)
    if found is None:
        return None

    g_vars, steps = found
    used = {step.replace("←", "").strip().split()[0] for step in steps}
    lines = [f"intro {' '.join(g_vars)}"] if g_vars else []
    for (name, lemma_vars, lhs, rhs), proof in lemmas:
        if name not in used:
            continue
        binder = " ".join(lemma_vars)
        head = f"have {name} : ∀ {binder} : G, {render(lhs)} = {render(rhs)} := by"
        body = "\n".join("  " + l for l in proof.split("\n"))
        lines.append(head + "\n" + body)
    lines.append("rfl" if not steps else f"rw [{', '.join(steps)}]")
    return "\n".join(lines)




def route_candidates(problem, limit=14):
    """Equations that sit between the hypothesis and the goal: every m with
    eq1 implies m and m implies eq2, both settled true in the table. Sorted
    by statement length, because short laws have short proofs."""
    pair = problem_ids(problem)
    if pair is None:
        return []
    a, b = pair
    try:
        cls, packed, ncls = _etp_tables()
    except Exception:
        return []

    def implies(x, y):
        pos = cls[x - 1] * ncls + cls[y - 1]
        return ((packed[pos >> 2] >> ((pos & 3) * 2)) & 3) == 1

    if not implies(a, b):
        return []
    reps = {}
    for eq in range(1, _ETP_N + 1):
        reps.setdefault(cls[eq - 1], eq)
    mids = []
    for mid in reps.values():
        if cls[mid - 1] in (cls[a - 1], cls[b - 1]):
            continue
        if implies(a, mid) and implies(mid, b):
            text = etp_equation(mid)
            if text:
                mids.append((len(text), mid, text))
    mids.sort()
    return [(mid, text) for _, mid, text in mids[:limit]]


def prove_leg(from_text, to_text, budget_s):
    """Prove one implication with the whole deterministic stack."""
    body = collapse_proof(from_text, to_text)
    if body is not None:
        return body
    try:
        body = rewrite_prove(from_text, to_text, budget_s=budget_s * 0.6)
    except Exception:
        body = None
    if body is not None:
        return body
    try:
        return lemma_prove(from_text, to_text, budget_s=budget_s * 0.4)
    except Exception:
        return None


def _intro_vars(body):
    """The variables a proof body introduces, in its own order."""
    first = body.split(chr(10), 1)[0].strip()
    if first.startswith("intro "):
        return first[6:].split()
    return []


def routed_prove(problem, budget_s=90):
    """Prove the goal by routing through an intermediate law. The middle law
    is proved from the hypothesis and emitted as a have block, then the goal
    is derived from hypothesis plus that lemma. The judge only ever sees
    ordinary rewriting; the table just chose the waypoint."""
    eq1_text = normalize(problem["equation1"])
    eq2_text = normalize(problem["equation2"])
    deadline = time.monotonic() + budget_s
    cands = route_candidates(problem)
    if not cands:
        return None
    h_rule = build_rule("h", eq1_text)

    for mid, raw in cands:
        if time.monotonic() > deadline:
            return None
        mid_text = normalize(raw)
        share = max(6.0, (deadline - time.monotonic()) / max(2, len(cands)))
        leg = prove_leg(eq1_text, mid_text, share)
        if leg is None:
            continue
        binder = _intro_vars(leg)
        m_rule = build_rule("m", mid_text)
        if sorted(binder) != sorted(m_rule[1]):
            continue
        found = _rewrite_search([h_rule, m_rule], eq2_text,
                                min(deadline, time.monotonic() + share),
                                5, 40000, compound_fills=True)
        if found is None:
            continue
        g_vars, steps = found
        lines = [f"intro {' '.join(g_vars)}"] if g_vars else []
        head = (f"have m : {chr(8704)} {' '.join(binder)} : G, {mid_text}"
                f" := by") if binder else f"have m : {mid_text} := by"
        lines.append(head)
        lines.extend("  " + l for l in leg.split(chr(10)))
        lines.append(f"rw [{', '.join(steps)}]" if steps else "rfl")
        return chr(10).join(lines)
    return None


# -- deterministic solve shared by both tracks -----------------------------

def solve_deterministic(problem, budget_s):
    """Return (verdict, code) if a deterministic certificate is found, else
    None. The budget splits toward the counterexample hunt, since a found
    table is checked before it ships while a rewrite chain can still fail
    at elaboration."""
    eq1_text = normalize(problem["equation1"])
    eq2_text = normalize(problem["equation2"])
    eq1 = parse_equation(eq1_text)
    eq2 = parse_equation(eq2_text)
    known = etp_verdict(problem)

    if known != 1:
        # Not a known true: the curated magmas are free, then the search.
        n, table = pool_counterexample(eq1, eq2)
        if n is not None:
            return "false", make_false_code(n, table)
        ce_budget = budget_s * (0.9 if known in (2, 3) else 0.7)
        n, table = find_counterexample(eq1, eq2, ce_budget)
        if n is not None:
            return "false", make_false_code(n, table)
        if known in (2, 3):
            return None

    body = collapse_proof(eq1_text, eq2_text)
    if body is not None:
        return "true", make_true_code(body)

    # Known true frees the counterexample share for deeper proof search.
    rw_budget = budget_s * (0.55 if known == 1 else 0.3)
    try:
        body = rewrite_prove(eq1_text, eq2_text, budget_s=rw_budget)
    except Exception:
        body = None
    if body is not None:
        return "true", make_true_code(body)
    if known == 1:
        for prover in (
            lambda: lemma_prove(eq1_text, eq2_text, budget_s=budget_s * 0.25),
            lambda: routed_prove(problem, budget_s=budget_s * 0.2),
        ):
            try:
                body = prover()
            except Exception:
                body = None
            if body is not None:
                return "true", make_true_code(body)
    return None


def build_analysis(problem, solved_false):
    notes = []
    known = etp_verdict(problem)
    if known == 1:
        notes.append("This implication is KNOWN TRUE. Respond with a proof; "
                     "never answer false.")
    elif known in (2, 3):
        notes.append("This implication is KNOWN FALSE. Respond with a "
                     "counterexample table only; never attempt a proof.")
    elif not solved_false:
        notes.append("No counterexample exists up to Fin 4, so this is almost certainly TRUE.")
    if collapse_proof(problem["equation1"], problem["equation2"]):
        notes.append("The hypothesis collapses every element to one value.")
    if known == 1:
        # Waypoints: laws that follow from h and imply the goal. Proving one
        # of them first is usually far easier than attacking the goal whole.
        try:
            cands = route_candidates(problem, limit=6)
        except Exception:
            cands = []
        if cands:
            listed = "; ".join(f"Equation{mid}: {text}" for mid, text in cands)
            notes.append("Each of these laws follows from h and implies the "
                         "goal, so proving one first then finishing from it "
                         "is a good route: " + listed + ".")
    return "Solver analysis: " + (" ".join(notes) if notes else "no deterministic shortcut found.")


# -- model response parsing ------------------------------------------------

def extract_json(text):
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    for candidate in (text, m.group() if m else None):
        if candidate:
            try:
                return json.loads(candidate)
            except Exception:
                pass
    return None


# Tactics the proof policy rejects or the judge routinely bounces; a body
# containing one is discarded before it wastes a judge call.
BANNED_TACTICS = re.compile(
    r"\b(sorry|admit|simp|simpa|aesop|omega|decide|tauto|norm_num|ring|"
    r"nlinarith|linarith|native_decide)\b"
)


def clean_proof_body(body):
    if ":= by" in body:
        body = re.sub(r"^.*?:=\s*by\s*\n?", "", body, count=1, flags=re.DOTALL)
    body = re.sub(r"^\s*by\s+", "", body)
    body = re.sub(r"^\s*import\s+.*\n?", "", body, flags=re.MULTILINE)
    body = body.strip()
    if BANNED_TACTICS.search(body):
        return ""
    return body


def code_from_answer(answer, eq1, eq2):
    """Turn a parsed model answer into Lean code, or None if unusable. A
    model counterexample is only forwarded when it verifies locally, so a
    problem whose equations did not parse cannot submit a false verdict.
    For true proofs the goal intro is imposed here: models regularly forget
    it, and that single omission rejected otherwise plausible proofs."""
    if answer.get("verdict") == "true":
        proof = clean_proof_body(answer.get("proof", ""))
        if not proof:
            return None
        if eq2 is not None and eq2[0]:
            proof = re.sub(r"^\s*intro[s]?\b[^\n]*\n?", "", proof, count=1)
            proof = f"intro {' '.join(eq2[0])}\n" + proof
        return make_true_code(proof)
    if answer.get("verdict") == "false" and eq1 is not None and eq2 is not None:
        tbl = answer.get("counterexample_table")
        try:
            if isinstance(tbl, list) and tbl and _witness(eq1, eq2, len(tbl), tbl):
                return make_false_code(len(tbl), tbl)
        except Exception:
            return None
    return None


# -- Solo track (stdin/stdout, interactive judge) --------------------------

def read_message():
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    return json.loads(line.strip())


def send_message(msg):
    print(json.dumps(msg), flush=True)


def run_solo():
    problem = dict(read_message()["problem"])
    for field in ("equation1", "equation2"):
        problem[field] = normalize(str(problem.get(field, "")))

    # A parse failure on an unusual equation spelling must never kill the
    # process; the model fallback can still answer without local analysis.
    try:
        eq1 = parse_equation(normalize(problem["equation1"]))
        eq2 = parse_equation(normalize(problem["equation2"]))
    except Exception:
        eq1 = eq2 = None

    det = None
    if eq1 is not None:
        try:
            det = solve_deterministic(problem, budget_s=420)
        except Exception:
            det = None
    solved_false = det is not None and det[0] == "false"
    if det is not None:
        send_message({"call": "judge", "verdict": det[0], "code": det[1]})
        if read_message().get("status") == "accepted":
            return

    try:
        analysis = build_analysis(problem, solved_false)
    except Exception:
        analysis = "Solver analysis: unavailable for this problem."
    # Bounded model loop: eight rounds is where returns flatten, and a clean
    # exit beats grinding into the wall-clock kill. If the model flounders
    # for three rounds, one deeper rewrite search often ends the argument
    # deterministically before more tokens burn.
    for rnd in range(8):
        if rnd == 3 and eq1 is not None and etp_verdict(problem) in (2, 3):
            # Known false and still unsolved: one long deeper hunt beats
            # asking the model for proofs that cannot exist.
            try:
                n2, tbl2 = find_counterexample(eq1, eq2, 400)
            except Exception:
                n2 = None
            if n2 is not None:
                send_message({"call": "judge", "verdict": "false",
                              "code": make_false_code(n2, tbl2)})
                if read_message().get("status") == "accepted":
                    return
        if rnd == 3 and eq1 is not None and etp_verdict(problem) != 2:
            # Two deterministic escalations while the model flounders: a
            # deeper direct chain, then the lemma-saturation prover that
            # chains derived consequences of h.
            for prover in (
                lambda: rewrite_prove(problem["equation1"], problem["equation2"],
                                      budget_s=150, max_depth=7, max_nodes=80000),
                lambda: lemma_prove(problem["equation1"], problem["equation2"],
                                    budget_s=180),
            ):
                try:
                    body = prover()
                except Exception:
                    body = None
                if body is None:
                    continue
                send_message({"call": "judge", "verdict": "true",
                              "code": make_true_code(body)})
                if read_message().get("status") == "accepted":
                    return
        send_message({"call": "llm", "context": {"round": str(rnd), "analysis": analysis}})
        result = read_message()
        if "error" in result:
            return
        answer = extract_json(result.get("response", ""))
        if not answer:
            continue
        code = code_from_answer(answer, eq1, eq2)
        if code is None:
            continue
        send_message({"call": "judge", "verdict": answer["verdict"], "code": code})
        if read_message().get("status") == "accepted":
            return


# -- Marathon track (manifest in, append-only JSONL out) -------------------

def append_answer(path, entry):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass


def marathon_prompt(problem, analysis):
    filled = PROMPT
    for key, val in {
        "{problem.equation1_id}": f"Equation{problem.get('eq1_id', '')}",
        "{problem.equation2_id}": f"Equation{problem.get('eq2_id', '')}",
        "{problem.equation1}": problem["equation1"],
        "{problem.equation2}": problem["equation2"],
        "{solver.analysis}": analysis,
        "{history.attempts}": "none",
    }.items():
        filled = filled.replace(key, val)
    return filled


def run_marathon():
    manifest = os.environ["JUDGE_MARATHON_MANIFEST"]
    output = os.environ["JUDGE_MARATHON_OUTPUT"]
    budget_s = float(os.environ.get("JUDGE_MARATHON_BUDGET_SECONDS", "3600"))
    deadline = time.monotonic() + budget_s
    tail = 10.0

    problems = []
    with open(manifest, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                try:
                    prob = json.loads(raw)
                    for field in ("equation1", "equation2"):
                        prob[field] = normalize(str(prob.get(field, "")))
                    problems.append(prob)
                except json.JSONDecodeError:
                    continue

    # Phase 1: deterministic certificates for every problem (no tokens).
    per_problem = max(2.0, (budget_s * 0.4) / max(1, len(problems)))
    unsolved = []
    for prob in problems:
        if time.monotonic() + tail >= deadline:
            break
        try:
            det = solve_deterministic(prob, budget_s=per_problem)
        except Exception:
            det = None
        if det is not None:
            append_answer(output, {"id": prob["id"], "verdict": det[0], "code": det[1]})
        else:
            unsolved.append(prob)

    # Phase 2: one guarded model attempt per unsolved problem, budget allowing.
    try:
        from marathon_llm import call_llm, budget_remaining
    except Exception:
        return

    for prob in unsolved:
        if time.monotonic() + tail >= deadline or budget_remaining() < 20000:
            break
        try:
            eq1 = parse_equation(prob["equation1"])
            eq2 = parse_equation(prob["equation2"])
            result = call_llm(marathon_prompt(prob, build_analysis(prob, False)))
            if "error" in result:
                break
            answer = extract_json(result.get("response", ""))
            if not answer:
                continue
            code = code_from_answer(answer, eq1, eq2)
            if code is not None:
                append_answer(output, {"id": prob["id"], "verdict": answer["verdict"], "code": code})
        except Exception:
            continue


def main():
    if "JUDGE_MARATHON_MANIFEST" in os.environ:
        run_marathon()
    else:
        run_solo()


if __name__ == "__main__":
    main()
