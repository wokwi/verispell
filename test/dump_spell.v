module dump ();
  initial begin
    $dumpfile("spell_test.vcd");
    $dumpvars(0, spell);
    #1;
  end
endmodule
