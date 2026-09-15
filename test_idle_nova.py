# Gate: the idle supernova state machine fires once per still period
# (random 9-15s), never while moving, never more often than the cooldown.
from shader_soul import idle_nova_due


def test_idle_nova():
    # still since t=0, armed for t=10: fires at 10, re-arms 9-15s later
    hit, fire_at = idle_nova_due(now=10.0, still_since=0.0, last_nova=-9.0,
                                fire_at=10.0, moving=False)
    assert hit and 19.0 <= fire_at <= 25.0, (hit, fire_at)
    # moving never fires, window re-arms from the move time
    hit, fa = idle_nova_due(now=30.0, still_since=29.0, last_nova=10.0,
                            fire_at=25.0, moving=True)
    assert not hit and 39.0 <= fa <= 45.0, fa
    # just before the window: hold
    hit, fa = idle_nova_due(now=24.9, still_since=24.0, last_nova=10.0,
                            fire_at=25.0, moving=False)
    assert not hit and fa == 25.0
    # at the window: fires, re-arms
    hit, fa = idle_nova_due(now=25.0, still_since=24.0, last_nova=10.0,
                            fire_at=25.0, moving=False)
    assert hit and 34.0 <= fa <= 40.0, fa
    # global 2s nova cooldown suppresses a fire right after one
    hit, fa = idle_nova_due(now=11.0, still_since=0.0, last_nova=10.0,
                            fire_at=10.9, moving=False)
    assert not hit and fa == 10.9
    print("IDLE NOVA OK")


test_idle_nova()
