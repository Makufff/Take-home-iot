// ChirpStack v4 payload codec for the LoRa node (Device profile -> Codec -> JavaScript).
// Uplink: [light_raw_hi, light_raw_lo, light_digital]
function decodeUplink(input) {
  var b = input.bytes;
  if (b.length < 3) {
    return { errors: ["expected 3 bytes, got " + b.length] };
  }
  return {
    data: {
      light_raw: (b[0] << 8) | b[1],
      light_digital: b[2]
    }
  };
}
